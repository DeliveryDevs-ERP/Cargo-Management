"""Versioned billing contracts for new Cargo Bookings; no historical recosting."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
import hashlib
import json

import frappe
from frappe import _


def decimal(value):
    try:
        result = Decimal(str(value or 0))
    except Exception:
        frappe.throw(_('Cargo quantities and financial values must be finite numbers.'))
    if not result.is_finite():
        frappe.throw(_('Cargo quantities and financial values must be finite numbers.'))
    return result


def quantity(row):
    if row.rate_type == 'Per Bag':
        return decimal(row.bag_qty)
    if row.rate_type == 'Per Weight(Ton)':
        return decimal(row.qty) * decimal(row.avg_weight)
    return decimal(row.qty)


def money(value):
    return decimal(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def billing_inputs(row):
    """Economic values, independent of JSON int/float and SQL Decimal spelling."""
    return (row.get('rate_type') or '', *(decimal(row.get(key)) for key in
        ('qty', 'rate', 'avg_weight', 'bag_qty', 'bag_weight')))


def prepare_booking(doc):
    before = doc.get_doc_before_save()
    if before and int(doc.get('cargo_billing_version') or 0) != int(before.get('cargo_billing_version') or 0):
        frappe.throw(_('A saved Cargo billing contract version cannot be changed.'))
    if not doc.get('cargo_billing_version'):
        return
    previous = {row.name: row for row in before.cargo_details} if before else {}
    from frappe.model.meta import get_field_precision
    currency=frappe.db.get_value('Company',doc.company,'default_currency') if doc.company else None
    precision=min(get_field_precision(frappe.get_meta(name).get_field('rate'),currency=currency)
                  for name in ('Sales Order Item','Sales Invoice Item'))
    rate_quantum=Decimal(10) ** -precision
    for row in doc.cargo_details:
        flags=frappe.db.get_value('Item',row.cargo_type,['enable_deferred_revenue','enable_deferred_expense'])
        if flags and any(flags):
            frappe.throw(_('Cargo source evidence verifies inactive deferred accounting. This Item requires a separately implemented and tested deferred-accounting binding; its flags will not be changed automatically.'))
        qty, rate = quantity(row), decimal(row.rate)
        if qty <= 0 or rate < 0 or decimal(row.qty) <= 0 or decimal(row.qty) != int(decimal(row.qty)):
            frappe.throw(_('Cargo requires positive whole physical allocations, a positive billing quantity and a non-negative rate.'))
        old = previous.get(row.name)
        inputs_changed = old is not None and (billing_inputs(old) != billing_inputs(row)
            or old.get('cargo_type') != row.get('cargo_type')
            or before.get('company') != doc.get('company'))
        signature = hashlib.sha256(json.dumps([str(value.normalize()) if isinstance(value, Decimal) else value
            for value in billing_inputs(row)]).encode()).hexdigest()
        if old and not inputs_changed and old.get('cargo_billing_input_hash'):
            signature = old.cargo_billing_input_hash  # Preserve recorded provenance on an unchanged contract.
        if inputs_changed:
            row.cargo_discrepancy_acknowledged = 0
            if row.cargo_billing_override:
                frappe.throw(_('Cargo billing inputs changed. Clear and explicitly re-approve the manual override.'))
        effective = rate.quantize(rate_quantum,rounding=ROUND_HALF_UP)
        if row.cargo_billing_override:
            frappe.only_for(('Cargo Manager', 'System Manager'))
            if not (row.cargo_override_reason or '').strip() or decimal(row.cargo_override_amount) < 0:
                frappe.throw(_('A manual Cargo override requires a reason and a non-negative amount.'))
        override_changed = old is not None and (
            bool(old.get('cargo_billing_override')) != bool(row.get('cargo_billing_override'))
            or (row.cargo_billing_override and decimal(old.get('cargo_override_amount')) != decimal(row.get('cargo_override_amount'))))
        preserve_native = (old is not None and not inputs_changed and not override_changed
            and old.get('cargo_billing_input_hash') and old.get('cargo_effective_rate') is not None
            and old.get('cargo_native_amount') is not None)
        if preserve_native:
            # Revalidate authority, but use the persisted contract's numbers.
            # Framework precision changes and forged read-only payload values
            # cannot silently reprice an unchanged saved Booking.
            row.cargo_effective_rate = old.cargo_effective_rate
            row.cargo_native_amount = old.cargo_native_amount
        elif row.cargo_billing_override:
            effective = (decimal(row.cargo_override_amount) / qty).quantize(rate_quantum, rounding=ROUND_HALF_UP)
            if money(qty * effective) != money(row.cargo_override_amount):
                frappe.throw(_('The requested Cargo override cannot be represented at native rate precision.'))
        if not preserve_native:
            row.cargo_effective_rate = float(effective)
            row.cargo_native_amount = float(money(qty * effective))
        row.cargo_billing_input_hash = signature
        if doc.docstatus == 1 and money(row.amount) != money(row.cargo_native_amount) and not row.cargo_discrepancy_acknowledged and not row.cargo_billing_override:
            frappe.throw(_('Entered Cargo Amount differs from native quantity × rate. Review and acknowledge the billing difference before submission.'))


def item_values(row, version=0):
    if not version:
        # Exact existing v16 mapping for unversioned/historical Bookings.
        if row.rate_type == 'Per Container':
            return dict(qty=row.qty, weight_per_unit=row.avg_weight, rate=row.rate, amount=row.amount)
        if row.rate_type in ('Per Weight(Ton)', 'Per Bag'):
            return dict(qty=row.bag_qty, weight_per_unit=row.bag_weight, rate=row.rate, amount=row.amount)
        return dict(qty=row.qty, rate=row.rate, amount=row.amount)
    values = dict(qty=float(quantity(row)), rate=row.cargo_effective_rate,
                  amount=row.cargo_native_amount, custom_cargo_detail=row.name)
    if row.rate_type == 'Per Container':
        values['weight_per_unit'] = row.avg_weight
    elif row.rate_type == 'Per Bag':
        values['weight_per_unit'] = row.bag_weight
    return values


def allocate_total(total, count, index, precision=2):
    """Conserve a non-negative total without negative rounding residuals."""
    total = decimal(total)
    if total < 0 or count < 1 or index < 0 or index >= count:
        frappe.throw(_('Invalid Cargo allocation total/count/index.'))
    quantum = Decimal(10) ** -precision
    unit = (total / count).quantize(quantum, rounding=ROUND_FLOOR)
    residual = total - unit * count
    whole = int(residual / quantum)
    return unit + (quantum if index >= count - whole else 0) + (residual - whole * quantum if index == count - 1 else 0)
