"""Resolve the source application's service labels without site-specific IDs."""
import frappe


def service_names(label, company=None, mode=None):
    from cargo_management.cargo_management.utils.configuration import catalog
    filters = {'name1': label}
    if mode:
        filters['transport_mode'] = mode
    if company is None:
        # Identity queries may span several authorized Companies. Their callers
        # must constrain actual documents through Booking/permission predicates.
        return frappe.get_all('Service Type', filters=filters, pluck='name', limit_page_length=0)
    return [row.name for row in catalog('Service Type', company, filters, fields=['name'])]


def is_service(name,label):
    return bool(name and frappe.db.get_value('Service Type',name,'name1')==label)
