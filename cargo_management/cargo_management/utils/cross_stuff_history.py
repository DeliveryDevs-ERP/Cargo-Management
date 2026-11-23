"""Atomic Cross-Stuff history retention; never reverses an accounting document.

Safe legacy behavior (full-weight transfers and replacement job order) remains.
Draft-invoiced downstream work is retired in place. Submitted financial history,
progressed work and unprovable reversals block before operational mutation.
"""
import json
import uuid

import frappe
from frappe import _

JOBS = ('FPLRoadJob', 'FPLRailJob', 'FPLYardJob', 'FPLCrossStuffJob')


def image(doc):
    return json.loads(frappe.as_json(doc.as_dict()))


def snapshot(freights, containers):
    result = {'freights': [], 'containers': [], 'jobs': [], 'requests': []}
    bookings = set()
    for name in sorted(freights):
        freight = frappe.get_doc('FPL Freight Orders', name, for_update=True)
        result['freights'].append(image(freight))
        bookings.add(freight.sales_order_number)
        for doctype in JOBS:
            rows = frappe.db.sql(f'SELECT name FROM `tab{doctype}` WHERE freight_order_id=%s ORDER BY name FOR UPDATE', name)
            for (row,) in rows:
                result['jobs'].append(image(frappe.get_doc(doctype, row, for_update=True)))
    result['containers'] = [image(frappe.get_doc('FPL Containers', name, for_update=True)) for name in sorted(containers)]
    for booking in sorted(bookings):
        for (name,) in frappe.db.sql('SELECT name FROM `tabContainer or Vehicle Request` WHERE booking_order_id=%s ORDER BY name FOR UPDATE', booking):
            result['requests'].append(image(frappe.get_doc('Container or Vehicle Request', name, for_update=True)))
    return result


def prepare(doc):
    from cargo_management.cargo_management.utils.configuration import booking_company
    company = booking_company(doc.booking_order_id, 'write')
    if not doc.grounded_filled_containers:
        frappe.throw(_('Cross-Stuff requires a verified source and receiving container allocation.'))
    containers = {row.container_number for row in doc.grounded_filled_containers} | {row.reference_container for row in doc.grounded_filled_containers}
    if None in containers or '' in containers:
        frappe.throw(_('Cross-Stuff source and receiving container references are required.'))
    sources = {row.container_number for row in doc.grounded_filled_containers}
    targets = {row.reference_container for row in doc.grounded_filled_containers}
    if sources & targets:
        frappe.throw(_('Cross-Stuff cannot use the same allocation as source and receiver.'))
    freight_names = set()
    # Ordered locks cover the whole transfer, not one row at a time.
    for name in sorted(containers):
        frappe.db.sql('SELECT name FROM `tabFPL Containers` WHERE name=%s FOR UPDATE', name)
        container = frappe.get_doc('FPL Containers', name, for_update=True)
        if container.booking_order_id != doc.booking_order_id or not container.freight_order_id:
            frappe.throw(_('Cross-Stuff cannot cross Booking or Company boundaries.'))
        freight_names.add(container.freight_order_id)
        active = frappe.db.sql('''SELECT DISTINCT train.name FROM `tabFPL Perform Middle Mile` train
            JOIN `tabFPL MM cdt` allocation ON allocation.parent=train.name
            WHERE allocation.container=%s AND train.status IN ('Train Formed','Loaded','Departed') LIMIT 1''', name)
        if active:
            frappe.throw(_('Release the container from its active train before Cross-Stuff processing.'))
    for name in sorted(freight_names):
        frappe.db.sql('SELECT name FROM `tabFPL Freight Orders` WHERE name=%s FOR UPDATE', name)
        freight = frappe.get_doc('FPL Freight Orders', name)
        freight.check_permission('write')
        if freight.sales_order_number != doc.booking_order_id:
            frappe.throw(_('Cross-Stuff Freight Order does not belong to its Booking.'))
    for name in sorted(sources):
        rows = [row for row in doc.grounded_filled_containers if row.container_number == name]
        freight = frappe.get_doc('FPL Freight Orders', frappe.db.get_value('FPL Containers', name, 'freight_order_id'))
        total = sum(float(row.weight_to_transfer or 0) for row in rows)
        if any(float(row.weight_to_transfer or 0) <= 0 for row in rows) or abs(total - float(freight.weight or 0)) > .000001:
            frappe.throw(_('Cross-Stuff must account for the full source weight; partial/unbalanced transfers are blocked.'))
        if any(abs(float(row.weight or 0) - float(freight.weight or 0)) > .000001 for row in rows):
            frappe.throw(_('Cross-Stuff source weight changed; reload and verify the allocation.'))
        if abs(sum(float(row.bags_to_transfer or 0) for row in rows) - float(freight.bag_qty or 0)) > .000001:
            frappe.throw(_('Cross-Stuff must conserve the source bag quantity.'))
    for target in targets:
        rate_types = {frappe.db.get_value('FPL Freight Orders', frappe.db.get_value('FPL Containers', row.container_number, 'freight_order_id'), 'rate_type')
                      for row in doc.grounded_filled_containers if row.reference_container == target}
        if len(rate_types) != 1:
            frappe.throw(_('Cross-Stuff cannot silently combine different billing rate types.'))
    before = snapshot(freight_names, containers)
    # Only downstream jobs are candidates for retirement/deletion; completed
    # upstream jobs are expected and must not be blocked or rewritten.
    for freight in before['freights']:
        source = any(freight['name'] == frappe.db.get_value('FPL Containers', value, 'freight_order_id') for value in sources)
        if not source:
            if float(freight.get('weight') or 0) > 0:
                frappe.throw(_('Cross-Stuff receiver already carries weight.'))
            continue
        cut = next((i for i, row in enumerate(freight['jobs']) if
            frappe.db.get_value('Service Type', row['job_name'], 'name1') == 'Cross Stuff'), None)
        if cut is not None:
            downstream = freight['jobs'][cut + 1:]
        else:
            cut = next((i for i, row in enumerate(freight['jobs']) if row['job_name'] == doc.job_before_cross_stuff), None)
            if cut is None:
                frappe.throw(_('Cross-Stuff predecessor is absent from the source job sequence.'))
            if cut > 0 and frappe.db.get_value('Service Type', freight['jobs'][cut-1]['job_name'], 'name1') == 'Gate Out':
                cut -= 1
            downstream = freight['jobs'][cut:]
        for row in downstream:
            old = next((job for job in before['jobs'] if job['name'] == row.get('job_id')), None)
            if old:
                validate_unstarted(old)
    journal = frappe.get_doc(dict(doctype='Cargo Cross Stuff Transfer', performance=doc.name,
        company=company, booking_order=doc.booking_order_id, state='Applied', before_state=frappe.as_json(before)))
    journal.insert(ignore_permissions=True)
    doc.flags.cargo_transfer_journal = journal
    frappe.flags.cargo_active_transfer = journal.name
    return journal


def validate_unstarted(job):
    if job.get('status') not in ('Draft', 'Assigned', None, '') or any(job.get(key) for key in
        ('start_time', 'started_at', 'completed_at', 'completion_time', 'start_date_and_time', 'actual_start_time', 'performance_details',
         'pickup_arrival', 'pickup_departure', 'dropoff_arrival', 'dropoff_completed', 'gate_in', 'gate_out')):
        frappe.throw(_('Progressed downstream Cargo work cannot be replaced automatically.'))
    for expense in job.get('expenses', []):
        for field, doctype in (('purchase_invoice_no', 'Purchase Invoice'), ('sales_invoice_no', 'Sales Invoice')):
            if expense.get(field):
                status = frappe.db.get_value(doctype, expense[field], 'docstatus')
                if status != 0:
                    frappe.throw(_('Submitted, cancelled or missing financial references block Cross-Stuff replacement.'))


def retire_or_delete(doc, rows):
    journal = doc.flags.cargo_transfer_journal
    before = json.loads(journal.before_state)
    for row in rows:
        if not row.job_id:
            continue
        old = next((job for job in before['jobs'] if job['name'] == row.job_id), None)
        if not old:
            frappe.throw(_('Downstream job is not present in the locked transfer before-image.'))
        validate_unstarted(old)
        retained = bool(old.get('expenses'))
        if retained:
            # No parent save: do not regenerate invoices or mutate old expense
            # rows. The original job remains the financial source of truth.
            frappe.db.set_value(old['doctype'], old['name'], {'cargo_retired': 1, 'cargo_transfer': journal.name}, update_modified=False)
        else:
            frappe.delete_doc(old['doctype'], old['name'])
        journal.append('mappings', dict(job_type=old['doctype'], job=old['name'], source_freight=row.parent,
            disposition='Retained financial history' if retained else 'Replaced unstarted work', before_image=frappe.as_json(old)))
        row.job_id = None
    journal.save(ignore_permissions=True)
    return rows


def finish(doc):
    journal = doc.flags.cargo_transfer_journal
    before = json.loads(journal.before_state)
    # Versioned new contracts move value without copying expenses or changing
    # the Booking/Sales Order contract. Legacy rate/weight behavior is retained.
    from cargo_management.cargo_management.utils.billing import decimal, money
    from decimal import ROUND_FLOOR, Decimal
    originals = {row['name']: row for row in before['freights']}
    allocations = {}
    sources = {row.container_number for row in doc.grounded_filled_containers}
    for container in sources:
        freight_name = frappe.db.get_value('FPL Containers', container, 'freight_order_id')
        original = originals[freight_name]
        if not original.get('cargo_billing_version'):
            continue
        transfers = [row for row in doc.grounded_filled_containers if row.container_number == container]
        remaining = money(original['cargo_contracted_revenue'])
        for index, row in enumerate(transfers):
            transferred = decimal(row.bags_to_transfer) if original['rate_type']=='Per Bag' else decimal(row.weight_to_transfer)
            quantity = decimal(original['bag_qty']) if original['rate_type']=='Per Bag' else decimal(original['weight'])
            if quantity <= 0:
                frappe.throw(_('Cross-Stuff source billing quantity is not positive.'))
            portion = remaining if index == len(transfers)-1 else (decimal(original['cargo_contracted_revenue']) * transferred / quantity).quantize(Decimal('.01'),rounding=ROUND_FLOOR)
            remaining -= portion
            target = frappe.db.get_value('FPL Containers', row.reference_container, 'freight_order_id')
            allocations[target] = allocations.get(target, decimal(0)) + portion
        frappe.db.set_value('FPL Freight Orders', freight_name, 'cargo_contracted_revenue', 0, update_modified=False)
    for target, revenue in allocations.items():
        values = {'cargo_billing_version':1,'cargo_contracted_revenue':float(revenue)}
        freight = frappe.get_doc('FPL Freight Orders', target)
        qty = decimal(freight.weight) if freight.rate_type == 'Per Weight(Ton)' else decimal(freight.bag_qty) if freight.rate_type == 'Per Bag' else decimal(1)
        if qty <= 0:
            frappe.throw(_('Cross-Stuff replacement billing quantity is not positive.'))
        values['rate'] = float(revenue/qty)
        frappe.db.set_value('FPL Freight Orders', target, values, update_modified=False)
    journal.after_state = frappe.as_json(snapshot({row['name'] for row in before['freights']}, {row['name'] for row in before['containers']}))
    journal.save(ignore_permissions=True)


def reverse(doc):
    name = frappe.db.get_value('Cargo Cross Stuff Transfer', {'performance': doc.name}, 'name')
    if not name:
        frappe.throw(_('Historical Cross-Stuff has no verified reversal journal; automatic cancellation is blocked.'))
    journal = frappe.get_doc('Cargo Cross Stuff Transfer', name)
    if journal.state == 'Reversed':
        return
    before, after = json.loads(journal.before_state), json.loads(journal.after_state)
    current = snapshot({row['name'] for row in before['freights']}, {row['name'] for row in before['containers']})
    if frappe.as_json(current) != frappe.as_json(after):
        frappe.throw(_('Cross-Stuff downstream state changed; automatic cancellation is unsafe.'))
    if doc.expenses or any(job.get('expenses') for job in before['jobs'] + current['jobs']):
        frappe.throw(_('Cost-bearing Cross-Stuff requires explicit financial retention/reversal review; invoices are never automatically cancelled.'))
    savepoint = 'cargo_cross_reverse_' + uuid.uuid4().hex[:12]
    frappe.db.savepoint(savepoint)
    try:
        original_jobs = {(row['doctype'], row['name']) for row in before['jobs']}
        # Remove only unchanged, unstarted, unreferenced replacement jobs. Their
        # owned FPL Jobs rows are replaced from the exact journal before-image.
        for row in current['jobs']:
            if (row['doctype'], row['name']) not in original_jobs:
                own_completed_cross = row['doctype'] == 'FPLCrossStuffJob' and row.get('performance_details') == doc.name and not row.get('expenses')
                if not own_completed_cross:
                    validate_unstarted(row)
                frappe.flags.cargo_reversing_crossstuff = doc.name if own_completed_cross else None
                frappe.delete_doc(row['doctype'], row['name'])
                frappe.flags.cargo_reversing_crossstuff = None
        for row in before['jobs']:
            if not frappe.db.exists(row['doctype'], row['name']):
                restored = frappe.get_doc(row)
                restored.insert(ignore_permissions=True, set_name=row['name'])
            else:
                frappe.get_doc(row).db_update()
        for kind in ('freights', 'containers', 'requests'):
            for row in before[kind]:
                restored = frappe.get_doc(row)
                restored.db_update()
                for table in restored.meta.get_table_fields():
                    # db_update by itself never restores child identities.
                    frappe.db.delete(table.options, {'parent': restored.name, 'parenttype': restored.doctype, 'parentfield': table.fieldname})
                    for child in restored.get(table.fieldname, []):
                        child.db_insert()
        journal.db_set('state', 'Reversed')
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    finally:
        frappe.flags.cargo_reversing_crossstuff = None
