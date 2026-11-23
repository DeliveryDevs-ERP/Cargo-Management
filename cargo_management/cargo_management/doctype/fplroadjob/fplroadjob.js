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
                    job_type: frm.doc.job_type,
                    self_freight_order: frm.doc.freight_order_id
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

async function populate_expenses(frm, job_mode) {
    // The server initializes fixed charges once and validates Company bindings.
    return set_cost_type_filter(frm, job_mode);
}

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
    if (row.purchase_invoice_no || row.sales_invoice_no) frappe.throw(__('Financially referenced Cargo expenses must be retained. Invoices are never deleted automatically.'));
},


    expenses_move: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log("Attempting to Move row:", row);
        frm.save();
    }
});

