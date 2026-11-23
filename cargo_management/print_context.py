"""Safe native invoice print context, independent of first-item descriptions."""
import re
from html import unescape

import frappe


def get_cargo_print_context(doc):
    doc.check_permission('read')
    from cargo_management.cargo_management.api.expense_billing import invoice_context
    context = invoice_context(doc) if doc.get('custom_booking_order') else None
    booking = frappe.get_doc('Booking Order', context.booking) if context else None
    containers = []
    if booking:
        containers = frappe.get_list('FPL Freight Orders', filters={'sales_order_number': booking.name, 'container_number': ['is', 'set']},
            fields=['name','container_number','size','weight'], order_by='name', limit_page_length=0)
    items = []
    for item in doc.items:
        description = item.description or item.item_name or item.item_code or ''
        size = re.search(r'Container Size:\s*([^,<>]+)', description)
        # ERPNext stores descriptions as sanitized HTML (including entities).
        # Convert to plain text once, then let the template escape that text;
        # escaping the stored HTML directly prints literal "&amp;" in PDFs.
        plain_description = unescape(frappe.utils.strip_html(description))
        items.append(dict(item=item, description=plain_description, size=size.group(1).strip() if size else ''))
    return dict(booking=booking, containers=containers, items=items,
                qr_url=frappe.utils.get_url_to_form('Sales Invoice', doc.name))
