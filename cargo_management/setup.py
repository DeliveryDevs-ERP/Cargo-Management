"""Minimal, repeatable integration schema; never seed operational business data."""
import frappe
from frappe import _
from frappe.utils import cint
from cargo_management.location import LOCATION_TYPES

CRYPTO_METHOD = 'cargo_management.tasks.crypto.pull_and_store'


def ensure_cargo_roles():
    for name in ('Cargo Operator', 'Cargo Manager'):
        if not frappe.db.exists('Role', name):
            frappe.get_doc(dict(doctype='Role', role_name=name, desk_access=1)).insert(ignore_permissions=True)

# Each field has a persisted consumer; Purchase Invoice transient assignments
# alone do not justify inventing further integration schema.
INTEGRATION_FIELDS = {
    'Sales Order': [dict(fieldname='custom_booking_order_id', label='Booking Order',
                         fieldtype='Link', options='Booking Order', insert_after='customer',
                         no_copy=1)],
    'Sales Invoice': [dict(fieldname='custom_booking_order', label='Booking Order',
                           fieldtype='Link', options='Booking Order', insert_after='customer',
                           no_copy=1)],
    'Location': [dict(fieldname='custom_location_type', label='Cargo Location Type',
                      fieldtype='Select', options='\n' + '\n'.join(LOCATION_TYPES),
                      mandatory_depends_on='eval:!!doc.__islocal', allow_in_quick_entry=1, insert_after='location_name',
                      description='Required for new Locations. Existing blank classifications are preserved.'),
                 dict(fieldname='custom_disabled', label='Disabled for Cargo',
                      fieldtype='Check', default='0', insert_after='custom_location_type')],
}


def ensure_integration_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    missing = {}
    for doctype, definitions in INTEGRATION_FIELDS.items():
        meta = frappe.get_meta(doctype)
        for definition in definitions:
            existing = meta.get_field(definition['fieldname'])
            if existing:
                if existing.fieldtype != definition['fieldtype'] or (existing.options or '') != definition.get('options', ''):
                    frappe.throw(_('Existing field {0}.{1} conflicts with the verified Cargo integration definition.').format(doctype, definition['fieldname']))
            else:
                missing.setdefault(doctype, []).append(definition.copy())
    if missing:
        create_custom_fields(missing, update=False)


def configure_crypto_schedule():
    enabled = bool(cint(frappe.conf.get('cargo_crypto_enabled', 0)))
    if enabled and not all(frappe.conf.get(k) for k in ['cargo_crypto_database_url', 'cargo_crypto_api_key']):
        frappe.throw(_('Crypto opt-in requires private database and API settings.'))
    name = frappe.db.get_value('Scheduled Job Type', {'method': CRYPTO_METHOD}, 'name')
    if name and bool(frappe.db.get_value('Scheduled Job Type', name, 'stopped')) == enabled:
        frappe.db.set_value('Scheduled Job Type', name, 'stopped', int(not enabled))


def set_crypto_enabled(enabled=False):
    """Explicit administrator/Bench opt-in. Never contacts the external services."""
    frappe.only_for('System Manager')
    enabled = cint(enabled)
    if enabled and not all(frappe.conf.get(k) for k in ['cargo_crypto_database_url', 'cargo_crypto_api_key']):
        frappe.throw(_('Configure private crypto credentials before opting in.'))
    from frappe.installer import update_site_config
    update_site_config('cargo_crypto_enabled', enabled)
    frappe.conf.cargo_crypto_enabled = enabled
    configure_crypto_schedule()
    frappe.clear_cache()
    return {'enabled': bool(enabled)}


def reconcile():
    from cargo_management.location import reconcile_location_type
    reconcile_location_type()
    ensure_integration_fields()
    from cargo_management.release_metadata import reconcile as reconcile_release
    reconcile_release()
    from cargo_management.workspace import reconcile as reconcile_workspace
    reconcile_workspace()
    configure_crypto_schedule()


def get_account_manager_emails(booking_order=None):
    users = frappe.get_all('Has Role', filters={'role': 'Accounts Manager', 'parenttype': 'User'}, pluck='parent')
    if not users:
        return []
    records=frappe.get_all('User', filters={'name': ['in', users], 'enabled': 1}, fields=['name','email'])
    return [row.email for row in records if not booking_order or frappe.has_permission('Booking Order','read',doc=booking_order,user=row.name)]


def has_app_permission():
    return bool(frappe.has_permission('Booking Order', 'read'))
