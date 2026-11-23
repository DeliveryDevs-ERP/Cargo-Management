"""Application metadata and empty-install checks on explicitly owned test sites."""
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import frappe
from frappe.model.base_document import get_controller
from cargo_management.tests.isolated_fixtures import require_disposable

ROOT=Path(__file__).parents[1]


def assert_metadata_only():
    require_disposable()
    req=json.loads((ROOT/'release_requirements.json').read_text())
    parents=[name for name in req['original_doctypes']+req['supporting_doctypes']
             if not frappe.get_meta(name).istable]
    forbidden=parents+['Company','Customer','Supplier','Item','Sales Order','Sales Invoice',
                       'Purchase Invoice','Payment Entry','Journal Entry','GL Entry','Auto Repeat']
    populated={name:frappe.db.count(name) for name in forbidden if frappe.db.count(name)}
    if populated:raise AssertionError('Installation created business records: '+str(populated))
    return dict(passed=True,business_records=0,checked=len(forbidden))


class TestCleanInstall(unittest.TestCase):
    def setUp(self):
        require_disposable()

    def test_all_models_controllers_fields_and_links(self):
        req=json.loads((ROOT/'release_requirements.json').read_text())
        names=req['original_doctypes']+req['supporting_doctypes']
        self.assertEqual(len(names),33)
        self.assertEqual(set(frappe.get_all('DocType',filters={'module':'Cargo Management'},pluck='name')),set(names))
        for name in names:
            with self.subTest(doctype=name):
                self.assertIsNotNone(get_controller(name))
                meta=frappe.get_meta(name)
                columns=frappe.db.get_table_columns(name)
                for field in meta.fields:
                    if field.fieldtype in ('Link','Table','Table MultiSelect') and field.options:
                        self.assertTrue(frappe.db.exists('DocType',field.options))
                    if field.fieldtype not in frappe.model.no_value_fields and not field.is_virtual:
                        self.assertIn(field.fieldname,columns)

    def test_owned_integration_fields_and_permissions(self):
        from cargo_management.setup import INTEGRATION_FIELDS
        from cargo_management.release_metadata import MISSING_FIELDS
        count=0
        for source in (INTEGRATION_FIELDS,MISSING_FIELDS):
            for dt,definitions in source.items():
                for definition in definitions:
                    count+=1
                    actual=frappe.get_meta(dt).get_field(definition['fieldname'])
                    self.assertEqual(actual.fieldtype,definition['fieldtype'])
                    self.assertEqual(actual.options or '',definition.get('options',''))
        self.assertEqual(count,17)
        for role in ('Cargo Operator','Cargo Manager'):
            self.assertTrue(frappe.db.get_value('Role',role,'desk_access'))
        self.assertTrue(frappe.get_meta('Sales Order').get_field('custom_booking_order_id').read_only)
        for path in (ROOT/'cargo_management/doctype').glob('*/*.json'):
            source=json.loads(path.read_text())
            actual={p.role:p for p in frappe.get_meta(source['name']).permissions}
            for row in source.get('permissions',[]):
                for grant in ('read','write','create','submit','cancel','delete'):
                    self.assertEqual(actual[row['role']].get(grant) or 0,row.get(grant) or 0,
                                     source['name']+'/'+row['role']+'/'+grant)

    def test_registered_reports_formats_workspace_and_branding(self):
        req=json.loads((ROOT/'release_requirements.json').read_text())
        self.assertEqual(len(req['reports']),16)
        for name in req['reports']:
            doc=frappe.get_doc('Report',name)
            self.assertFalse(doc.disabled)
            slug=frappe.scrub(name)
            self.assertTrue(callable(importlib.import_module('cargo_management.cargo_management.report.'+slug+'.'+slug).execute))
        for name in req['print_formats']:
            self.assertFalse(frappe.get_doc('Print Format',name).disabled)
        workspace=frappe.get_doc('Workspace','Cargo Management')
        self.assertTrue(workspace.public)
        self.assertTrue(workspace.shortcuts)
        self.assertTrue(frappe.db.exists('Module Onboarding','CargoManagement'))
        from cargo_management import hooks
        self.assertEqual(hooks.app_home,'/desk/cargo-management')
        logo=ROOT/'public/images/cargo-management-logo.webp'
        self.assertTrue(logo.read_bytes().startswith(b'RIFF'))
        self.assertEqual(hooks.add_to_apps_screen[0]['logo'],'/assets/cargo_management/images/cargo-management-logo.webp')

    def test_crypto_is_disabled_and_optional_driver_is_unnecessary(self):
        from cargo_management.tasks import crypto
        from cargo_management.setup import CRYPTO_METHOD
        self.assertFalse(frappe.conf.get('cargo_crypto_enabled'))
        self.assertEqual(frappe.db.get_value('Scheduled Job Type',{'method':CRYPTO_METHOD},'stopped'),1)
        with patch.object(crypto,'psycopg2',None),patch.object(crypto.requests,'get') as http:
            self.assertEqual(crypto.pull_and_store(),{'status':'disabled'})
            http.assert_not_called()

    def test_guest_has_no_cargo_app_or_report_authority(self):
        user=frappe.session.user
        try:
            frappe.set_user('Guest')
            from cargo_management.setup import has_app_permission
            self.assertFalse(has_app_permission())
            from frappe.desk.query_report import get_report_doc
            with self.assertRaises(frappe.PermissionError):get_report_doc('Booking PNL')
        finally:frappe.set_user(user)

    def test_crypto_enabled_path_uses_only_mocked_provider_and_database(self):
        import sys
        from types import ModuleType
        from unittest.mock import MagicMock
        from cargo_management.tasks import crypto
        driver=ModuleType('psycopg2')
        extras=ModuleType('psycopg2.extras')
        driver.extras=extras
        driver.connect=MagicMock()
        extras.execute_batch=MagicMock()
        response=MagicMock(status_code=200)
        response.json.return_value={'status':{'timestamp':'2026-01-01T00:00:00Z'},'data':[
            {'id':1,'symbol':'TEST','name':'Synthetic asset','quote':{'USD':{'price':2}}}]}
        original=dict(frappe.conf)
        try:
            frappe.conf.update(cargo_crypto_enabled=1,cargo_crypto_api_key='test-only',cargo_crypto_database_url='test-only')
            with patch.dict(sys.modules,{'psycopg2':driver,'psycopg2.extras':extras}),\
                 patch.object(crypto.requests,'get',return_value=response) as http,patch.object(frappe,'log_error'):
                crypto.pull_and_store()
                self.assertFalse(http.call_args.kwargs['allow_redirects'])
                extras.execute_batch.assert_called_once()
                self.assertEqual(extras.execute_batch.call_args.args[2][0]['price'],2)
                driver.connect.return_value.close.assert_called_once()
        finally:
            frappe.conf.clear();frappe.conf.update(original)
