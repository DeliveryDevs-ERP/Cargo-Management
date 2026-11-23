"""Cargo's verified Location choices without rewriting historical blanks."""
import frappe
from frappe import _

LOCATION_TYPES = (
    'Yard', 'Warehouse', 'Airport', 'Seaport', 'Rail Terminal',
    'Distribution Center', 'Cross-Dock Facility', 'Container Depot',
)


def validate_location(doc, method=None):
    value = doc.get('custom_location_type') or ''
    if value and value not in LOCATION_TYPES:
        frappe.throw(_('Choose a valid Cargo Location Type.'))
    before = doc.get_doc_before_save()
    if not value and (doc.is_new() or (before and before.get('custom_location_type'))):
        frappe.throw(_('Cargo Location Type is required for new Locations and cannot be cleared once classified.'))


def reconcile_location_type():
    """Only the Cargo-owned classifier may transition from Data to Select."""
    name = frappe.db.get_value('Custom Field', {'dt': 'Location', 'fieldname': 'custom_location_type'}, 'name')
    if not name:
        return  # Fresh installation creates the reviewed definition normally.
    field = frappe.get_doc('Custom Field', name)
    options = '\n' + '\n'.join(LOCATION_TYPES)
    if field.fieldtype not in ('Data', 'Select'):
        frappe.throw(_('Cargo Location Type conflicts with the verified integration definition.'))
    invalid = frappe.db.sql('''SELECT name,custom_location_type FROM `tabLocation`
        WHERE COALESCE(custom_location_type,'')<>'' AND custom_location_type NOT IN %s''', (LOCATION_TYPES,))
    if invalid:
        frappe.throw(_('Existing Cargo Location classifications require review before updating the choices.'))
    desired = dict(fieldtype='Select', options=options, reqd=0, allow_in_quick_entry=1,
                   mandatory_depends_on='eval:!!doc.__islocal',
                   description='Required for new Locations. Existing blank classifications are preserved.')
    if any(field.get(key) != value for key, value in desired.items()):
        field.update(desired)
        field.save()
