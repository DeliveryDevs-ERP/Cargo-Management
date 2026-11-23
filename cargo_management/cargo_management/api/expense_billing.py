"""Cargo-only extra billing, typed provenance, native authority and atomic claims."""
import json
import frappe
from frappe import _

PARENTS = ('FPLRoadJob', 'FPL Perform Middle Mile', 'Perform Cross Stuff', 'FPLYardJob')


def billing_authority():
    frappe.only_for(('Accounts User', 'Accounts Manager', 'Cargo Manager', 'System Manager'))
    if not frappe.has_permission('Sales Invoice', 'create'):
        frappe.throw(_('Sales Invoice creation permission is required.'), frappe.PermissionError)


def invoice_context(doc):
    booking = doc.get('custom_booking_order')
    sales_orders = {row.sales_order for row in doc.items if row.sales_order}
    if len(sales_orders) > 1:
        frappe.throw(_('Cargo invoices require one unambiguous Sales Order.'))
    for name in sales_orders:
        order = frappe.get_doc('Sales Order', name)
        order.check_permission('read')
        if booking and order.custom_booking_order_id != booking:
            frappe.throw(_('Cargo Invoice and Sales Order refer to different Bookings.'))
        booking = booking or order.custom_booking_order_id
        if order.company != doc.company or order.customer != doc.customer or order.docstatus == 2:
            frappe.throw(_('Cargo Sales Order Company/customer/status is incompatible with this invoice.'))
    if not booking:
        return None
    order = frappe.get_doc('Booking Order', booking)
    order.check_permission('read')
    if order.company != doc.company or order.bill_to != doc.customer:
        frappe.throw(_('Cargo Invoice Company/customer differs from its Booking.'))
    if not sales_orders:
        matches = frappe.get_list('Sales Order', filters={'custom_booking_order_id': booking, 'docstatus': ['<', 2]}, pluck='name', limit_page_length=0)
        if len(matches) != 1:
            frappe.throw(_('Cargo invoice requires one verified Sales Order binding.'))
        sales_orders = set(matches)
    return frappe._dict(booking=booking, company=order.company, customer=doc.customer, sales_order=next(iter(sales_orders)))


def expense_context(parent, row):
    if parent.doctype not in PARENTS or row.parenttype != parent.doctype or row.parent != parent.name or row.parentfield != 'expenses':
        frappe.throw(_('Invalid Cargo expense parent/type/child reference.'))
    booking = parent.get('booking_order_id') if parent.doctype == 'Perform Cross Stuff' else parent.get('sales_order_number')
    if row.container_number:
        container = frappe.get_doc('FPL Containers', row.container_number)
        if booking and booking != container.booking_order_id:
            frappe.throw(_('Expense container belongs to another Booking.'))
        booking = container.booking_order_id
        if parent.get('freight_order_id') and parent.freight_order_id != container.freight_order_id:
            frappe.throw(_('Expense container belongs to another Freight Order.'))
    elif parent.doctype == 'FPL Perform Middle Mile':
        frappe.throw(_('Train expenses require an exact container allocation.'))
    from cargo_management.cargo_management.utils.configuration import booking_company, validate_binding
    company = booking_company(booking)
    if parent.get('company') and parent.company != company:
        frappe.throw(_('Expense parent Company differs from its Booking.'))
    cost = validate_binding('FPL Cost Type', row.expense_type, company)
    from cargo_management.expense_controls import MODES
    if cost.job_mode != MODES[parent.doctype]:
        frappe.throw(_('Expense Cost Type does not belong to this Cargo operation.'))
    if not cost.item_id:
        frappe.throw(_('Cargo Cost Type requires an expense Item.'))
    return frappe._dict(booking=booking, company=company, cost=cost)


def eligible_rows(booking):
    for doctype in PARENTS:
        if not frappe.has_permission(doctype, 'read'):
            continue
        filters = {'sales_order_number': booking} if doctype in ('FPLRoadJob', 'FPLYardJob') else {'booking_order_id': booking} if doctype == 'Perform Cross Stuff' else {}
        for name in frappe.get_list(doctype, filters=filters, pluck='name', limit_page_length=0):
            parent = frappe.get_doc(doctype, name)
            parent.check_permission('read')
            for row in parent.get('expenses', []):
                if row.invoiced_ and not row.sales_invoice_no:
                    scope = expense_context(parent, row)
                    if scope.booking == booking:
                        yield parent, row, scope


@frappe.whitelist()
def fetch_expenses_items(sales_invoice_number):
    billing_authority()
    base = frappe.get_doc('Sales Invoice', sales_invoice_number)
    base.check_permission('read')
    scope = invoice_context(base)
    if not scope or base.is_return or base.is_debit_note or base.docstatus == 2:
        frappe.throw(_('Select a valid base Cargo Sales Invoice.'))
    conversion = float(base.conversion_rate or 0)
    if conversion <= 0:
        frappe.throw(_('A verified positive invoice currency conversion rate is required.'))
    expenses = []
    for parent, row, context in eligible_rows(scope.booking):
        reserved = frappe.db.sql('''SELECT i.parent FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` p ON p.name=i.parent
            WHERE i.custom_cargo_expense_row=%s AND p.docstatus<2 LIMIT 1''', row.name)
        if reserved:
            continue
        item = frappe.get_doc('Item', context.cost.item_id)
        expenses.append(dict(item_code=item.name, item_name=item.item_name, uom=item.stock_uom, qty=1,
            rate=float(row.amount) / conversion, amount=float(row.amount) / conversion,
            description=f'Expense from {parent.doctype} - {parent.name} - {row.name}',
            income_account=frappe.db.get_value('Company', scope.company, 'default_income_account'), sales_order=scope.sales_order,
            custom_cargo_expense_parenttype=parent.doctype, custom_cargo_expense_parent=parent.name, custom_cargo_expense_row=row.name))
    return dict(expenses=expenses, custom_booking_order=scope.booking, sales_order=scope.sales_order,
                company=scope.company, customer=scope.customer, currency=base.currency, conversion_rate=base.conversion_rate)


def get_filtered_records_by_container(doctype, fieldname, booking_order):
    if doctype not in PARENTS or fieldname != 'expenses':
        frappe.throw(_('Unsupported Cargo expense source.'))
    return list({parent.name: parent for parent, _, _ in eligible_rows(booking_order) if parent.doctype == doctype}.values())


def source_rows(doc, require_submitted_base=False):
    typed = [item for item in doc.items if item.get('custom_cargo_expense_row')]
    if not doc.get('custom_booking_order') and not typed:
        return []
    context = invoice_context(doc)
    if not doc.is_debit_note or not doc.return_against:
        if typed:
            frappe.throw(_('Expense references are allowed only on Cargo extra-charge debit invoices.'))
        return []
    billing_authority()
    if not context or len(typed) != len(doc.items) or not typed or doc.is_return:
        frappe.throw(_('Cargo extra charges require typed source references on every item.'))
    base = frappe.get_doc('Sales Invoice', doc.return_against)
    base.check_permission('read')
    original = invoice_context(base)
    if not original or original.booking != context.booking or base.company != doc.company or base.customer != doc.customer or base.currency != doc.currency or base.is_return or base.is_debit_note:
        frappe.throw(_('Cargo extra-charge invoice does not match its base invoice.'))
    if (require_submitted_base and base.docstatus != 1) or base.docstatus == 2 or base.name == doc.name:
        frappe.throw(_('Cargo extra charges require a submitted base invoice before posting.'))
    ids = [item.custom_cargo_expense_row for item in typed]
    if len(ids) != len(set(ids)):
        frappe.throw(_('A Cargo expense cannot be billed twice in one invoice.'))
    for name in sorted(ids):
        frappe.db.sql('SELECT name FROM `tabExpenses cdt` WHERE name=%s FOR UPDATE', name)
    result = []
    from cargo_management.cargo_management.utils.billing import money, decimal
    for item in typed:
        if item.custom_cargo_expense_parenttype not in PARENTS:
            frappe.throw(_('Unsupported Cargo expense parent.'))
        parent = frappe.get_doc(item.custom_cargo_expense_parenttype, item.custom_cargo_expense_parent)
        parent.check_permission('read')
        row = frappe.get_doc('Expenses cdt', item.custom_cargo_expense_row, for_update=True)
        scope = expense_context(parent, row)
        if scope.booking != context.booking or scope.company != context.company or not row.invoiced_:
            frappe.throw(_('Expense is not billable by this Cargo Booking/Company.'))
        if row.sales_invoice_no and row.sales_invoice_no != doc.name:
            frappe.throw(_('Cargo expense has already been invoiced.'))
        if item.item_code != scope.cost.item_id or decimal(item.qty) != 1 or money(item.base_net_amount) != money(row.amount):
            frappe.throw(_('Cargo expense Item, quantity or Company-currency amount was changed.'))
        if item.sales_order != context.sales_order:
            frappe.throw(_('Cargo expense Sales Order reference was changed.'))
        duplicate = frappe.db.sql('''SELECT i.parent FROM `tabSales Invoice Item` i
            INNER JOIN `tabSales Invoice` p ON p.name=i.parent
            WHERE i.custom_cargo_expense_row=%s AND p.docstatus<2 AND p.name<>%s
            LIMIT 1 FOR UPDATE''', (row.name, doc.name))
        if duplicate:
            frappe.throw(_('Cargo expense is already reserved by another invoice.'))
        result.append(row)
    return result


def validate_cargo_invoice(doc, method=None):
    # ERPNext's native Sales Order mapper preserves item.sales_order, but the
    # differently named Cargo Booking fields are not copied automatically.
    # Bind only new Cargo drafts; never backfill existing/historical invoices
    # or impose Cargo's single-order rule on ordinary ERPNext invoices.
    if doc.is_new() and not doc.get('custom_booking_order') and any(
        row.sales_order and frappe.db.get_value('Sales Order', row.sales_order, 'custom_booking_order_id')
        for row in doc.items
    ):
        doc.custom_booking_order = invoice_context(doc).booking
    source_rows(doc)


def before_submit(doc, method=None):
    source_rows(doc, require_submitted_base=True)


@frappe.whitelist()
def update_expense_references(doc, method):
    from frappe.model.document import Document
    if not isinstance(doc,Document):
        frappe.throw(_('This Cargo hook requires a native Document event context.'),frappe.PermissionError)
    doc.check_permission('submit')
    if doc.get('custom_booking_order') and doc.is_debit_note and doc.return_against:
        if doc.doctype!='Sales Invoice' or doc.docstatus!=1 or frappe.db.get_value('Sales Invoice',doc.name,'docstatus')!=1:
            frappe.throw(_('Expense claims require the actual submitted native Sales Invoice.'))
    for row in source_rows(doc, require_submitted_base=True):
        update_claim(row, doc.name, 'claimed', doc.name)


def update_claim(row, invoice, action, reference):
    history = json.loads(row.get('cargo_invoice_history') or '[]')
    if (action=='claimed' and row.sales_invoice_no==reference and history
            and history[-1].get('invoice')==invoice and history[-1].get('action')==action):
        return  # Repeated native on_submit delivery preserves the exact audit history.
    history.append(dict(invoice=invoice, action=action, user=frappe.session.user, at=str(frappe.utils.now_datetime())))
    frappe.db.set_value('Expenses cdt', row.name, {'sales_invoice_no': reference, 'cargo_invoice_history': json.dumps(history)}, update_modified=False)


def release_cancelled_invoice(doc, method=None):
    if not (doc.get('custom_booking_order') and doc.is_debit_note and doc.return_against):
        return
    for item in doc.items:
        if item.get('custom_cargo_expense_row'):
            frappe.db.sql('SELECT name FROM `tabExpenses cdt` WHERE name=%s FOR UPDATE', item.custom_cargo_expense_row)
            row = frappe.get_doc('Expenses cdt', item.custom_cargo_expense_row)
            if row.sales_invoice_no != doc.name:
                frappe.throw(_('Expense billing reference changed; cancellation requires review.'))
            update_claim(row, doc.name, 'released_after_native_cancellation', None)


def before_cancel(doc, method=None):
    """Validate source claims before native cancellation writes any ledger."""
    if not (doc.get('custom_booking_order') and doc.is_debit_note and doc.return_against):
        return
    for row in source_rows(doc, require_submitted_base=True):
        if row.sales_invoice_no != doc.name:
            frappe.throw(_('Expense billing reference changed; cancellation requires review.'))
