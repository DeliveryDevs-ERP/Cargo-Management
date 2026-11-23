"""Use native transactional series without resetting existing counters or names."""
import frappe
from frappe.model.naming import make_autoname


def freight_name(prefix, booking=None):
    if prefix not in ('FO-', 'CFO-'):
        raise ValueError('Unsupported Cargo document prefix')
    if booking and booking.startswith('BO-DEMO-'):
        import hashlib
        prefix += 'DEMO-' + hashlib.sha256(booking.encode()).hexdigest()[:8].upper() + '-'
    # Old releases generated names without a series counter. Advance through
    # collisions instead of importing/resetting the counter from old records.
    for _ in range(10000):
        name = make_autoname(prefix + '.####', doctype='FPL Freight Orders')
        if not frappe.db.exists('FPL Freight Orders', name):
            return name
    frappe.throw('Existing Cargo document names exceed the safe naming reconciliation bound.')
