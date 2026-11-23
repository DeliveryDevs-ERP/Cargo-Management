"""Evidence-backed additive metadata, without operational seeds or native grants."""
import json
from pathlib import Path

import frappe
from frappe import _

MISSING_FIELDS = {
    'Purchase Invoice': [
        dict(fieldname='custom_midway_details', label='Cargo Details', fieldtype='Section Break', insert_after='amended_from'),
        dict(fieldname='custom_train_number', label='Train Number', fieldtype='Data', insert_after='custom_midway_details', in_list_view=1, translatable=1),
        dict(fieldname='custom_movement_type', label='Movement Type', fieldtype='Data', insert_after='custom_train_number', translatable=1),
    ],
    'Booking Order': [
        dict(fieldname='custom_section_break_415f3', fieldtype='Section Break', insert_after='delivery_date'),
        dict(fieldname='auto_repeat', label='Auto Repeat', fieldtype='Link', options='Auto Repeat', insert_after='amended_from', read_only=1, no_copy=1),
    ],
    'FPL Freight Orders': [
        dict(fieldname='custom_column_break_oc69a', fieldtype='Column Break', insert_after='container_type'),
        dict(fieldname='custom_section_break_eywky', label='Container Details', fieldtype='Section Break', insert_after='column_break_auic'),
    ],
    'Perform Cross Stuff': [
        dict(fieldname='auto_repeat', label='Auto Repeat', fieldtype='Link', options='Auto Repeat', insert_after='expenses', read_only=1, no_copy=1),
    ],
    'Sales Invoice Item': [
        dict(fieldname='custom_cargo_expense_parenttype', label='Cargo Expense Type', fieldtype='Data', insert_after='description', read_only=1, no_copy=1),
        dict(fieldname='custom_cargo_expense_parent', label='Cargo Expense Document', fieldtype='Data', insert_after='custom_cargo_expense_parenttype', read_only=1, no_copy=1),
        dict(fieldname='custom_cargo_expense_row', label='Cargo Expense Row', fieldtype='Data', insert_after='custom_cargo_expense_parent', read_only=1, no_copy=1),
        dict(fieldname='custom_cargo_detail', label='Cargo Booking Row', fieldtype='Data', insert_after='custom_cargo_expense_row', read_only=1, no_copy=1),
    ],
    'Sales Order Item': [
        dict(fieldname='custom_cargo_detail', label='Cargo Booking Row', fieldtype='Data', insert_after='description', read_only=1, no_copy=1),
    ],
}


def merge_field_order(current, prior, required, accepted_legacy=()):
    """Repair only approved Cargo sequences, retaining every foreign field slot."""
    if (not isinstance(prior, list) or any(not isinstance(n, str) for n in prior)
            or len(prior) != len(set(prior)) or set(prior) - set(current)):
        raise ValueError('Unrecognized Cargo field-order customization.')
    if set(required) - set(current):
        raise ValueError('Required Cargo fields are missing from effective metadata.')
    owned = set(required)
    present = [name for name in prior if name in owned]
    ordered = prior + [name for name in current if name not in prior]
    complete = [name for name in ordered if name in owned]
    if present != required and complete != required and present not in accepted_legacy and complete not in accepted_legacy:
        raise ValueError('Existing Cargo field order conflicts with the release; review before changing.')
    replacements = iter(required)
    return [next(replacements) if name in owned else name for name in ordered]


def reconcile():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    for doctype, definitions in MISSING_FIELDS.items():
        missing = []
        for definition in definitions:
            current = frappe.get_meta(doctype).get_field(definition['fieldname'])
            if current:
                if current.fieldtype != definition['fieldtype'] or (current.options or '') != definition.get('options', ''):
                    frappe.throw(_('Cargo metadata conflict at {0}.{1}; refusing overwrite.').format(doctype, definition['fieldname']))
            else:
                missing.append(definition)
        if missing:
            create_custom_fields({doctype: missing}, update=False)
    # Only this verified integration property changes on a standard DocType.
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    field = frappe.get_meta('Sales Order').get_field('custom_booking_order_id')
    if not field.read_only:
        make_property_setter('Sales Order', 'custom_booking_order_id', 'read_only', 1, 'Check')
    # Field orders are relative legacy orders; never discard new/current fields.
    requirements = json.loads((Path(__file__).parent / 'release_requirements.json').read_text())
    for row in requirements['field_orders']:
        current = frappe.get_meta(row['doctype'])
        names = [field.fieldname for field in current.fields]
        desired = row['field_order'] + [name for name in names if name not in row['field_order']]
        existing = frappe.db.get_value('Property Setter', {'doc_type': row['doctype'], 'property': 'field_order', 'doctype_or_field': 'DocType'}, ['name', 'value'], as_dict=True)
        encoded = json.dumps(desired)
        if existing:
            try:
                prior = json.loads(existing.value)
            except (TypeError, ValueError):
                frappe.throw(_('Unrecognized Cargo field-order customization.'))
            try:
                desired = merge_field_order(names, prior, row['field_order'], row.get('accepted_legacy_orders', ()))
            except ValueError as error:
                frappe.throw(_(str(error)))
            encoded=json.dumps(desired)
        if not existing or existing.value != encoded:
            make_property_setter(row['doctype'], None, 'field_order', encoded, 'Data', for_doctype=True)
    sync_owned_documents(requirements)


def sync_owned_documents(requirements):
    """Older standard-record timestamps must not hide the reviewed package delta.

    Reconcile only explicitly registered Cargo documents and only when their
    packaged fields differ. Runtime-resolved shortcut service IDs are compared
    by the separate semantic workspace reconciler, not overwritten repeatedly.
    """
    module = Path(__file__).parent / 'cargo_management'
    targets = [('Report', 'report', name) for name in requirements['reports']]
    targets += [('Print Format', 'print_format', name) for name in requirements['print_formats']]
    targets += [('Workspace', 'workspace', 'Cargo Management')]
    targets += [('Notification', 'notification', name) for name in ('Expenses Intimation', 'Over Expenses Intimation')]
    ignored = {'modified', 'modified_by', 'creation', 'owner', 'idx', 'docstatus'}

    def matches(expected, actual):
        for key, value in expected.items():
            if key in ignored or (key == 'stats_filter' and expected.get('type') == 'DocType'):
                continue
            found = actual.get(key)
            if isinstance(value, list):
                if len(value) != len(found or []): return False
                if any(not matches(left, right) for left, right in zip(value, found or [])): return False
            elif key in ('content', 'format_data') and isinstance(value, str) and found:
                if json.loads(value) != json.loads(found): return False
            elif value not in (None, '') or found not in (None, ''):
                if value != found: return False
        return True

    for doctype, folder, name in targets:
        slug = frappe.scrub(name)
        source = module / folder / slug / (slug + '.json')
        if not source.is_file():
            if doctype == 'Notification': continue
            frappe.throw(_('Missing registered Cargo metadata source: {0}').format(name))
        desired = json.loads(source.read_text())
        if desired['name'] != name or desired.get('module') != 'Cargo Management':
            frappe.throw(_('Cargo metadata ownership guard failed.'))
        current = frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else None
        if current and current.get('module') not in ('Cargo Management', None, ''):
            frappe.throw(_('A differently owned metadata record uses the Cargo name {0}.').format(name))
        if current is None or not matches(desired, current):
            frappe.reload_doc('cargo_management', folder, slug, force=True)
