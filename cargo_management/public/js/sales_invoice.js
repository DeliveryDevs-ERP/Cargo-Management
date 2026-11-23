// Cargo-only extra-charge action. Native invoices retain the native toolbar.
frappe.ui.form.on('Sales Invoice', {
    refresh(frm) {
        if (frm.doc.docstatus !== 1 || !frm.doc.custom_booking_order || frm.doc.is_return || frm.doc.is_debit_note
            || !frappe.model.can_create('Sales Invoice')
            || !frappe.user_roles.some(role => ['Accounts User', 'Accounts Manager', 'Cargo Manager', 'System Manager'].includes(role))) return;
        frm.add_custom_button(__('Invoice for Extra Charges'), async () => {
            const response = await frappe.call({
                method: 'cargo_management.cargo_management.api.fetch_expenses_items.fetch_expenses_items',
                args: {sales_invoice_number: frm.doc.name}, freeze: true,
            });
            const scope = response.message;
            if (!scope || !scope.expenses.length) {
                frappe.msgprint(__('No eligible unbilled Cargo expenses.'));
                return;
            }
            await frappe.model.with_doctype('Sales Invoice');
            const invoice = frappe.model.get_new_doc('Sales Invoice');
            Object.assign(invoice, {
                company: scope.company, customer: scope.customer, currency: scope.currency,
                conversion_rate: scope.conversion_rate, return_against: frm.doc.name,
                is_debit_note: 1, custom_booking_order: scope.custom_booking_order,
                posting_date: frappe.datetime.now_date(),
            });
            scope.expenses.forEach(values => Object.assign(frappe.model.add_child(invoice, 'items'), values));
            const saved = await frappe.db.insert(invoice);
            frappe.set_route('Form', 'Sales Invoice', saved.name);
        }, __('Create'));
    },
});
