frappe.ui.form.on("FPLRoadJob", {


    refresh: function(frm) {
        if (frm.doc.freight_order_id) {
            frappe.db.get_value('FPL Freight Orders', frm.doc.freight_order_id, 'size')
                .then(r => {
                    if (r.message.size === 20) {
                        frm.set_df_property('double_20_', 'hidden', false);
                    } else {
                        frm.set_df_property('double_20_', 'hidden', true);
                    }
                });
        }
    },

    before_insert: function(frm){
        populate_expenses(frm, 'Truck Job'); 
    },

    after_save: function(frm){
        if (frm.doc.container_number_to_link){
            frappe.call({
                method: "cargo_management.cargo_management.doctype.fplroadjob.fplroadjob.sync_with_linked_job",
                args: {
                    docname: frm.doc.name 
                },
            });
        }
    },

    setup: function(frm) {        
        set_container_name_filter(frm);
        set_cost_type_filter(frm, 'Truck Job');

        // Setup for container_number_to_link field
        frm.fields_dict['container_number_to_link'].get_query = function(doc) {
            if (!frm.doc.job_type) {
                frappe.msgprint("Please specify a Job Type before selecting a container.");
                return;
            }
            return {
                query: 'cargo_management.cargo_management.doctype.fplroadjob.query.get_applicable_containers',
                filters: {
                    'job_start_location': frm.doc.job_start_location,
                    'not_in_container_number': frm.doc.container_number
                }
            };
        };   
    },


    container_number_to_link: function(frm) {
        if (frm.doc.container_number_to_link) {
            frappe.call({
                method: "cargo_management.cargo_management.doctype.fplroadjob.fplroadjob.link_container",
                args: {
                    container_number_to_link: frm.doc.container_number_to_link,
                    self_container_number: frm.doc.container_number,
                    job_type: frm.doc.job_type
                },
                callback: function(response) {
                    if (response.message) {
                        frappe.msgprint(response.message);
                    }
                }
            });
        }
    },
});

function populate_expenses(frm, job_mode) {
    // First, fetch cost types
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
                console.log('Fetched Cost Types:', response.message);
                response.message.forEach(function(cost_obj) {
                    if (cost_obj.fixed_ == 1) {
                        let row = frm.add_child('expenses');
                        row.expense_type = cost_obj.name;
                        row.amount = cost_obj.cost;
                    }
                });
                frm.refresh_field('expenses');
            }
        }
    });

    if (frm.doc.container_number && frm.doc.freight_order_id) {
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "FPL Containers",
                filters: {
                    container_number: frm.doc.container_number,
                    freight_order_id: frm.doc.freight_order_id
                },
                fieldname: 'name'
            },
            callback: function(r) {
                if (r.message) {
                    console.log('Fetched Container:', r.message);
                    // Update the container_number in expenses after fetching
                    let expenses = frm.doc.expenses;
                    expenses.forEach(function(expense) {
                        expense.container_number = r.message.name;
                    });
                    frm.refresh_field('expenses');
                }
            }
        });
    }
}

function set_cost_type_filter(frm, job_mode) {
    frm.fields_dict['expenses'].grid.get_field('expense_type').get_query = function() {
        return {
            filters: {
                job_mode: job_mode
            }
        };
    };
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

// frappe.ui.form.on('Expenses cdt', {
//     before_expenses_remove: function(frm, cdt, cdn) {
//         const row = locals[cdt][cdn];
//         console.log("Attempting to delete row:", row);

//         if (row.purchase_invoice_no) {
//             frappe.db.get_doc("Purchase Invoice", row.purchase_invoice_no)
//                 .then(PI => {
//                     console.log("Fetched PI:", PI);
//                     if (PI.docstatus === 0) {
//                         frappe.db.delete_doc('Purchase Invoice', PI.name)
//                             .then(() => {
//                                 frm.save_or_update();
//                             })
//                             .catch(err => {
//                                 console.error('Error deleting Purchase Invoice:', err);
//                                 frappe.msgprint(__('Row with Purchase Invoice No cannot be deleted.'), __('Not Allowed'));
//                                 throw new frappe.ValidationError();
//                             });
//                     } else if (PI.docstatus === 1) {
//                         frappe.throw(__("You cannot delete this ro1w"))
//                         frm.reload()
//                     }
//                 })
//                 .catch(err => {
//                     console.error("Error fetching Purchase Invoice:", err);
//                     throw new frappe.ValidationError();
//                 });
//         }
//     }
// });

frappe.ui.form.on('Expenses cdt', {
    before_expenses_remove: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log("Attempting to delete row:", row);

        if (row.purchase_invoice_no) {
            frappe.db.get_doc("Purchase Invoice", row.purchase_invoice_no)
                .then(PI => {
                    // console.log("Fetched PI:", PI);
                    if (PI.docstatus === 0) {
                        // If the PI is in draft status, allow deletion
                        frappe.db.delete_doc('Purchase Invoice', PI.name)
                            .then(() => {
                                if (frm.doc.double_20_ === 1) {
                                    frappe.msgprint("Please remove this row manually from other double 20 Road Job");
                                } 
                                frm.save();                        
                            })
                            .catch(err => {
                                console.error('Error deleting Purchase Invoice:', err);
                                frappe.msgprint(__('An error occurred while deleting the Purchase Invoice.'), __('Error'));
                                throw new frappe.ValidationError();
                            });
                    } else if (PI.docstatus === 1) {
                        // If the PI is submitted, do not allow deletion and reload the form
                        frappe.msgprint({
                            title: __('Not Allowed'),
                            message: __('Rows linked to a submitted Purchase Invoice cannot be deleted.'),
                            indicator: 'red'
                        });
                        frm.reload_doc();
                    }
                })
                .catch(err => {
                    console.error("Error fetching Purchase Invoice:", err);
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('Failed to fetch the Purchase Invoice linked to this row.'),
                        indicator: 'red'
                    });
                    frm.reload_doc(); // Reload the document in case of fetch error too
                });

            // Prevent the default deletion action until the promise is resolved
            frappe.validated = false;
        }
    },


    expenses_move: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log("Attempting to Move row:", row);
        frm.save();
    }
});

