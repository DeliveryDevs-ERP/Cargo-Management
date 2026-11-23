"""Preserve this local site's outbound opt-out without restricting accounting.

ERPNext permissions, document events, SQL and financial scheduler methods are
unchanged. Crypto also retains its independent disabled-by-default setting.
This application policy is not a container network firewall.
"""
from functools import wraps
from urllib.parse import urlsplit

import frappe

BLOCKED_PREFIXES = (
    'cargo_management.tasks.crypto.', 'frappe.integrations.',
    'erpnext.erpnext_integrations.', 'frappe.email.',
    'frappe.utils.telemetry.', 'frappe.automation_engine.',
)
BLOCKED_METHODS = {
    'frappe.utils.change_log.check_for_update',
    'frappe.core.doctype.security_settings.security_settings_alert.check_security_txt_expiry',
    'erpnext.utilities.doctype.video.video.update_youtube_data',
    'erpnext.projects.doctype.project.send_project_status_email_to_users',
    'erpnext.projects.doctype.project.project.send_project_status_email_to_users',
    'erpnext.setup.doctype.email_digest.email_digest.send',
    'erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.send_auto_email',
    'erpnext.crm.doctype.email_campaign.email_campaign.send_email_to_leads_or_contacts',
}


def active():
    """The existing local outbound opt-out needs no QA configuration flag."""
    return getattr(frappe.local, 'site', None) == 'erp16.local'


def method_name(method):
    if method is None:
        return ''
    return method if isinstance(method, str) else f'{method.__module__}.{method.__qualname__}'


def blocked_job(method):
    name = method_name(method)
    return name in BLOCKED_METHODS or name.startswith(BLOCKED_PREFIXES)


def check_url(url):
    parsed = urlsplit(str(url))
    if active() and not (
        parsed.scheme in ('http', 'https')
        and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        and parsed.port in (8000, 8002, 9002)
    ):
        frappe.throw('Unverified external HTTP integrations are disabled locally.', frappe.PermissionError)


def install(*args, **kwargs):
    """Install only HTTP controls; no SQL, document or mail-capture patching."""
    if not active():
        return
    import requests.sessions

    if not getattr(requests.sessions.Session.request, '_cargo_outbound_safety', False):
        original_request = requests.sessions.Session.request

        @wraps(original_request)
        def request(session, method, url, *a, **kw):
            check_url(url)
            return original_request(session, method, url, *a, **kw)

        request._cargo_outbound_safety = True
        requests.sessions.Session.request = request

    if not getattr(requests.sessions.Session.send, '_cargo_outbound_safety', False):
        original_send = requests.sessions.Session.send

        @wraps(original_send)
        def send(session, prepared, *a, **kw):
            check_url(prepared.url)
            return original_send(session, prepared, *a, **kw)

        send._cargo_outbound_safety = True
        requests.sessions.Session.send = send


def before_job(method=None, kwargs=None, **unused):
    install()
    if not active():
        return
    name = method_name(method)
    if name == 'frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job':
        values = kwargs or {}
        # The persisted scheduled method, not its caller-supplied log tag, wins.
        name = (frappe.db.get_value('Scheduled Job Type', values['scheduled_job_type'], 'method')
                if values.get('scheduled_job_type') else values.get('job_type'))
        if not name:
            frappe.throw('Unknown scheduled job is not authorized.', frappe.PermissionError)
    if name and blocked_job(name):
        frappe.throw('Unverified outbound integration jobs are disabled locally.', frappe.PermissionError)


class OutboundScheduledJobs:
    def enqueue(self, *args, **kwargs):
        if active() and (self.stopped or blocked_job(self.method)):
            return False
        return super().enqueue(*args, **kwargs)


def background_probe(nonce, queue_name):
    """Compatibility probe for local queue diagnostics; no ledger operations."""
    install()
    if not active():
        raise RuntimeError('The local outbound opt-out must be active')
    try:
        check_url('https://unverified.invalid/queue-probe')
    except frappe.PermissionError:
        return dict(site=frappe.local.site, nonce=nonce, queue=queue_name,
                    safeguards=['external HTTP blocked before network'], business_writes=False)
    raise RuntimeError('The local outbound opt-out failed')
