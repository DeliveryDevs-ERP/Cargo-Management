// Financial-only action for retained costs; never submits an invoice.
if (!frappe._cargo_expense_actions_loaded) {
frappe._cargo_expense_actions_loaded = true;
for (const doctype of ['FPLRoadJob','FPLYardJob','Perform Cross Stuff','FPL Perform Middle Mile']) {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (frm.is_new() || !frappe.model.can_create('Purchase Invoice')
                || !(frm.doc.expenses || []).some(row => !row.purchase_invoiced_created)) return;
            frm.add_custom_button(__('Create Pending Purchase Invoices'), async () => {
                if (frm.is_dirty()) frappe.throw(__('Save or reload the expense parent first.'));
                const response = await frm.call('create_pending_purchase_invoices');
                await frm.reload_doc();
                frappe.msgprint(__('Created {0} draft Purchase Invoices.', [(response.message || []).length]));
            });
        },
    });
}
}
