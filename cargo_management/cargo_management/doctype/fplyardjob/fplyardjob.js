// Copyright (c) 2024, Osama and contributors
// For license information, please see license.txt

frappe.ui.form.on("FPLYardJob", {
	before_insert: function(frm) {
        populate_expenses(frm, 'Yard Job');
    },

    refresh: function(frm) {
        set_cost_type_filter(frm, 'Yard Job');
        set_container_name_filter(frm);
    },
});

async function set_cost_type_filter(frm, job_mode) {
    if (!frm.doc.company && !frm.doc.sales_order_number && !frm.doc.booking_order_id) return;
    const identity = JSON.stringify([frm.doc.name, frm.doc.company, frm.doc.sales_order_number, frm.doc.booking_order_id]);
    const response = await frappe.call({
        method: 'cargo_management.expense_controls.get_cost_catalog',
        args: {doctype: frm.doctype, docname: frm.is_new?.() ? null : frm.doc.name,
            booking: frm.doc.booking_order_id || frm.doc.sales_order_number, company: frm.doc.company},
    });
    if (identity !== JSON.stringify([frm.doc.name, frm.doc.company, frm.doc.sales_order_number, frm.doc.booking_order_id])) return;
    const names = (response.message || []).map(row => row.name);
    frm.fields_dict.expenses.grid.get_field('expense_type').get_query = () => ({filters: {name: ['in', names], job_mode}});
}

async function populate_expenses(frm, job_mode) {
    // The server initializes fixed charges once and validates Company bindings.
    return set_cost_type_filter(frm, job_mode);
}

function set_container_name_filter(frm) {
    frm.fields_dict['expenses'].grid.get_field('container_number').get_query = function() {
        return {
            filters: {
                container_number : frm.doc.container_number,
                freight_order_id : frm.doc.freight_order_id
            }
        };
    };
}



frappe.ui.form.on('Expenses cdt', {
    before_expenses_remove: function(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.purchase_invoice_no || row.sales_invoice_no) frappe.throw(__('Financially referenced Cargo expenses must be retained. Invoices are never deleted automatically.'));
},

    expenses_move: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log("Attempting to Move row:", row);
        frm.save();
    }
});

