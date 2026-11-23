"""Server-owned Company cost bindings shared by job and performance forms."""
import frappe

MODES = {'FPLRoadJob': 'Truck Job', 'FPLYardJob': 'Yard Job',
         'Perform Cross Stuff': 'Cross Stuff Job', 'FPL Perform Middle Mile': 'Train Job'}


@frappe.whitelist()
def get_cost_catalog(doctype, docname=None, booking=None, company=None):
    """Read costs without syncing an obsolete whole document into a live form."""
    if doctype not in MODES:
        frappe.throw('Unsupported Cargo expense parent.')
    if docname:
        doc = frappe.get_doc(doctype, docname)
        doc.check_permission('read')
    else:
        if booking:
            frappe.get_doc('Booking Order', booking).check_permission('read')
        if company:
            frappe.get_doc('Company', company).check_permission('read')
        doc = frappe.get_doc(dict(doctype=doctype, company=company,
            booking_order_id=booking, sales_order_number=booking))
        doc.check_permission('create')
    return doc.get_cargo_costs()


def company_for(doc):
    from cargo_management.cargo_management.utils.configuration import booking_company, train_company
    if doc.doctype == 'FPL Perform Middle Mile':
        return doc.company or train_company(doc)
    return booking_company(doc.get('booking_order_id') or doc.get('sales_order_number'))


class CargoExpenseControls:
    @frappe.whitelist()
    def create_pending_purchase_invoices(self):
        """Procure retained costs without elevated permissions or job replay."""
        import uuid
        if self.doctype not in MODES or self.is_new():
            frappe.throw('Save the Cargo expense parent before creating draft invoices.')
        if not frappe.has_permission('Purchase Invoice','create'):
            frappe.throw('Purchase Invoice creation permission is required.',frappe.PermissionError)
        current=frappe.get_doc(self.doctype,self.name,for_update=True)
        current.check_permission('write')
        from cargo_management.cargo_management.api.expense_billing import expense_context
        before={row.purchase_invoice_no for row in current.expenses if row.purchase_invoice_no}
        for row in current.expenses:
            expense_context(current,row)
            if row.purchase_invoice_no and not row.purchase_invoiced_created:
                frappe.throw('An existing Cargo invoice reference has inconsistent flags; it will not be duplicated.')
        point='cargo_pending_purchase_'+uuid.uuid4().hex[:12]
        frappe.db.savepoint(point)
        try:
            current.create_purchase_invoice()
            # Road validation normally persists these fields through the parent
            # save. This explicit financial-only action must also work on a
            # retired parent, so persist only native-created child references.
            for row in current.expenses:
                if row.purchase_invoice_no and row.purchase_invoice_no not in before:
                    frappe.db.set_value('Expenses cdt',row.name,dict(purchase_invoice_no=row.purchase_invoice_no,
                        purchase_invoiced_created=1),update_modified=False)
            current.reload()
            return sorted({row.purchase_invoice_no for row in current.expenses if row.purchase_invoice_no}-before)
        except Exception:
            frappe.db.rollback(save_point=point)
            raise

    @frappe.whitelist()
    def get_cargo_costs(self):
        self.check_permission('create' if self.is_new() else 'read')
        from cargo_management.cargo_management.utils.configuration import catalog
        from cargo_management.cargo_management.utils.getSupplierForCostType import get_supplier
        company = company_for(self)
        costs = catalog('FPL Cost Type', company, {'job_mode': MODES[self.doctype]})
        for cost in costs:
            cost['supplier'] = get_supplier(cost.name, company)
        return costs


def initialize_fixed_costs(doc, method=None):
    if doc.doctype not in MODES or not doc.is_new() or doc.get('expenses') or doc.get('cargo_transfer') or doc.doctype == 'FPL Perform Middle Mile':
        return
    if not (doc.get('booking_order_id') or doc.get('sales_order_number')):
        return
    from cargo_management.cargo_management.utils.configuration import catalog
    from cargo_management.cargo_management.utils.getSupplierForCostType import get_supplier
    company = company_for(doc)
    for cost in catalog('FPL Cost Type', company, {'job_mode': MODES[doc.doctype], 'fixed_': 1, 'cost': ['>', 0]}):
        doc.append('expenses', dict(expense_type=cost.name, amount=cost.cost, client=get_supplier(cost.name, company)))
