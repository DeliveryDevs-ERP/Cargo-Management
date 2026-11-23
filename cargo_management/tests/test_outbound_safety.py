"""Local outbound opt-out and native accounting hooks; no site or SQL writes."""
from contextlib import ExitStack
import runpy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import frappe
import requests
from frappe.database.database import Database
from cargo_management import outbound_safety as policy


class TestOutboundSafety(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.calls = []
        self.fake = SimpleNamespace(local=SimpleNamespace(site='erp16.local'),
            PermissionError=frappe.PermissionError, db=SimpleNamespace(get_value=Mock()))

        def reject(message, exception):
            raise exception(message)

        self.fake.throw = reject
        self.stack.enter_context(patch.object(policy, 'frappe', self.fake))

        def request(*args, **kwargs):
            self.calls.append(('request', args, kwargs))
            return 'local-request'

        def send(*args, **kwargs):
            self.calls.append(('send', args, kwargs))
            return 'local-send'

        self.stack.enter_context(patch.object(requests.sessions.Session, 'request', request))
        self.stack.enter_context(patch.object(requests.sessions.Session, 'send', send))

    def test_local_outbound_default_needs_no_qa_flag(self):
        self.assertTrue(policy.active())
        self.assertFalse(hasattr(self.fake, 'conf'))
        self.fake.local.site = 'another.local'
        self.assertFalse(policy.active())

    def test_install_never_patches_sql_or_email(self):
        original_sql, original_mail = Database.sql, frappe.sendmail
        policy.install()
        self.assertIs(Database.sql, original_sql)
        self.assertIs(frappe.sendmail, original_mail)
        self.assertFalse(hasattr(policy, 'financial_document'))

    def test_install_is_idempotent(self):
        policy.install()
        first = requests.sessions.Session.request, requests.sessions.Session.send
        policy.install()
        self.assertEqual(first, (requests.sessions.Session.request, requests.sessions.Session.send))

    def test_local_web_and_realtime_remain_available(self):
        policy.install()
        for url in ('http://127.0.0.1:8000/login', 'http://localhost:8002/printview',
                    'http://[::1]:9002/socket.io/'):
            with self.subTest(url=url):
                self.assertEqual(requests.Session().request('GET', url), 'local-request')
                self.assertEqual(requests.Session().send(SimpleNamespace(url=url)), 'local-send')

    def test_external_direct_and_prepared_requests_never_reach_network(self):
        policy.install()
        for url in ('https://unverified.invalid/', 'http://localhost:1234/',
                    'http://127.0.0.1.unverified.invalid:8000/', 'file:///etc/hosts'):
            with self.subTest(url=url):
                with self.assertRaises(frappe.PermissionError):
                    requests.Session().request('GET', url)
                with self.assertRaises(frappe.PermissionError):
                    requests.Session().send(SimpleNamespace(url=url))
        self.assertEqual(self.calls, [])

    def test_redirect_destination_is_checked_again(self):
        policy.install()
        requests.Session().send(SimpleNamespace(url='http://localhost:8000/'))
        with self.assertRaises(frappe.PermissionError):
            requests.Session().send(SimpleNamespace(url='https://unverified.invalid/redirect'))
        self.assertEqual(len(self.calls), 1)

    def test_other_sites_do_not_inherit_local_policy(self):
        policy.install()
        self.fake.local.site = 'another.local'
        self.assertEqual(requests.Session().request('GET', 'https://unverified.invalid/'), 'local-request')

    def test_financial_and_native_maintenance_jobs_are_not_filtered(self):
        for method in (
            'erpnext.controllers.accounts_controller.update_invoice_status',
            'erpnext.accounts.deferred_revenue.process_deferred_accounting',
            'erpnext.accounts.utils.auto_create_exchange_rate_revaluation_daily',
            'erpnext.assets.doctype.asset.depreciation.post_depreciation_entries',
            'erpnext.stock.doctype.repost_item_valuation.repost_item_valuation.repost_entries',
            'frappe.automation.doctype.auto_repeat.auto_repeat.make_auto_repeat_entry',
            'frappe.core.doctype.log_settings.log_settings.run_log_clean_up',
            'frappe.monitor.flush',
        ):
            with self.subTest(method=method):
                self.assertFalse(policy.blocked_job(method))
                policy.before_job(method, {})

    def test_crypto_email_and_external_jobs_remain_filtered(self):
        for method in ('cargo_management.tasks.crypto.pull_and_store', 'frappe.email.queue.flush',
                       'frappe.integrations.doctype.webhook.webhook.enqueue_webhook',
                       'erpnext.setup.doctype.email_digest.email_digest.send'):
            with self.subTest(method=method):
                self.assertTrue(policy.blocked_job(method))
                with self.assertRaises(frappe.PermissionError):
                    policy.before_job(method, {})

    def test_persisted_unsafe_schedule_cannot_be_disguised_by_log_tag(self):
        self.fake.db.get_value.return_value = 'frappe.email.queue.flush'
        with self.assertRaises(frappe.PermissionError):
            policy.before_job('frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job',
                {'scheduled_job_type': 'persisted-record', 'job_type': 'frappe.monitor.flush'})
        self.fake.db.get_value.assert_called_once_with('Scheduled Job Type', 'persisted-record', 'method')

    def test_unknown_saved_schedule_fails_closed(self):
        self.fake.db.get_value.return_value = None
        with self.assertRaises(frappe.PermissionError):
            policy.before_job('frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job',
                {'scheduled_job_type': 'missing-record'})

    def test_native_stopped_setting_and_queue_arguments_are_preserved(self):
        class Native:
            def enqueue(self, *args, **kwargs):
                return args, kwargs

        class Job(policy.OutboundScheduledJobs, Native):
            stopped = 0
            method = 'erpnext.controllers.accounts_controller.update_invoice_status'

        job = Job()
        self.assertEqual(job.enqueue(force=True), ((), {'force': True}))
        job.stopped = 1
        self.assertFalse(job.enqueue(force=True))
        job.stopped = 0
        job.method = 'frappe.email.queue.flush'
        self.assertFalse(job.enqueue(force=True))


class TestAccountingHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hooks = runpy.run_path(str(Path(policy.__file__).with_name('hooks.py')))

    def test_no_wildcard_financial_document_hooks(self):
        self.assertNotIn('*', self.hooks['doc_events'])
        self.assertEqual(self.hooks['before_request'], ['cargo_management.outbound_safety.install'])
        self.assertEqual(self.hooks['before_job'], ['cargo_management.outbound_safety.before_job'])

    def test_cargo_invoice_validation_claims_and_cancellation_checks_remain(self):
        self.assertEqual(self.hooks['doc_events']['Sales Invoice'], {
            'validate': 'cargo_management.cargo_management.api.expense_billing.validate_cargo_invoice',
            'before_submit': 'cargo_management.cargo_management.api.expense_billing.before_submit',
            'on_submit': 'cargo_management.cargo_management.api.Sales_inv_validation_overload.update_expense_references',
            'before_cancel': 'cargo_management.cargo_management.api.expense_billing.before_cancel',
            'on_cancel': 'cargo_management.cargo_management.api.expense_billing.release_cancelled_invoice',
        })

    def test_company_scope_and_expense_history_checks_remain(self):
        for doctype in ('FPLRoadJob', 'FPLYardJob', 'FPLRailJob', 'FPLCrossStuffJob'):
            self.assertEqual(self.hooks['has_permission'][doctype], 'cargo_management.permissions.has_permission')
            self.assertEqual(self.hooks['doc_events'][doctype]['before_validate'],
                             'cargo_management.permissions.validate_expense_history')


if __name__ == '__main__':
    unittest.main()
