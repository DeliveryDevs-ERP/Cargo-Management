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

function set_cost_type_filter(frm, job_mode) {
    frm.fields_dict['expenses'].grid.get_field('expense_type').get_query = function() {
        return {
            filters: {
                job_mode: job_mode
            }
        };
    };
}

function populate_expenses(frm, job_mode) {
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "FPL Cost Type",
            filters: {
                job_mode: job_mode
            },
            fields: ["*"]
        },
        callback: function(response) {
            if (response.message) {
                frm.clear_table("expenses");
                console.log('Fetched Cost Types:', response.message);

                response.message.forEach(function(cost_obj) {
                    if (cost_obj.fixed_ == 1) {
                        let row = frm.add_child('expenses');
                        row.expense_type = cost_obj.name;
                        row.amount = cost_obj.cost;
                    }
                });
            }
        }
    });
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
        console.log("Attempting to delete row:", row);

        if (row.purchase_invoice_no) {
            frappe.db.get_doc("Purchase Invoice", row.purchase_invoice_no)
                .then(PI => {
                    console.log("Fetched PI:", PI);
                    if (PI.docstatus === 0) {
                        frappe.db.delete_doc('Purchase Invoice', PI.name)
                            .then(() => {
                                frm.save_or_update();
                            })
                            .catch(err => {
                                console.error('Error deleting Purchase Invoice:', err);
                                frappe.msgprint(__('Row with Purchase Invoice No cannot be deleted.'), __('Not Allowed'));
                                throw new frappe.ValidationError();
                            });
                    } else if (PI.docstatus === 1) {
                        frappe.msgprint(__('Row with Purchase Invoice No cannot be deleted.'), __('Not Allowed'));
                        console.error('Attempted to delete a submitted Purchase Invoice');
                        throw new frappe.ValidationError();
                    }
                })
                .catch(err => {
                    console.error("Error fetching Purchase Invoice:", err);
                    throw new frappe.ValidationError();
                });
        }
    }
});
