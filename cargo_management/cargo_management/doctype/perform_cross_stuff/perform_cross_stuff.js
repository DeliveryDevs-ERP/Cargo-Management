frappe.ui.form.on("Perform Cross Stuff", {

    before_insert: function(frm){
        populate_expenses(frm, 'Cross Stuff Job'); 
    },

    setup: function(frm) {
        // This is a reversible provenance backlink, not a dependent transaction
        // to cancel. The server restores it from the verified transfer journal
        // in before_cancel, and still rejects cost-bearing/changed history.
        frm.ignore_doctypes_on_cancel_all = [...new Set([
            ...(frm.ignore_doctypes_on_cancel_all || []), 'Container or Vehicle Request'
        ])];
        set_cost_type_filter(frm, 'Cross Stuff Job');
        frm.set_query('job_before_cross_stuff', function() {
            return {
                query: 'cargo_management.cargo_management.doctype.perform_cross_stuff.query.get_unique_service_types',
                filters: {booking_order_id: frm.doc.booking_order_id},
            };
        });
    },

    refresh: function(frm) {
        frm.set_query("container_number", "expenses", function(doc, cdt, cdn) {
            console.log("Setting container number query");

            let existingContainers = [];
            frm.doc.grounded_filled_containers.forEach(function(row) {
                if (row.container_number) {
                    existingContainers.push(row.container_number);
                }
                if (row.reference_container) {
                    existingContainers.push(row.reference_container);
                }
            });

            let filters = { };
            if (existingContainers.length > 0) {
                filters["name"] = ["in", existingContainers];
            }

            return { filters: filters };
        });    
    },

    
    onload: function(frm){
        console.log("Setting BO");
        set_cost_type_filter(frm, 'Cross Stuff Job');
        frm.set_query('booking_order_id', function() {
            return {
                query: 'cargo_management.cargo_management.doctype.perform_cross_stuff.query.get_BOs_name'
            };
        });
    },

    job_before_cross_stuff: function(frm) {
        if (frm.doc.booking_order_id && frm.doc.job_before_cross_stuff) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'FPL Freight Orders',
                    filters: {
                        sales_order_number: frm.doc.booking_order_id,
                        name: ['like', 'FO-%']
                    },
                    fields: ['name'],
                    limit_page_length: 1  // Fetch only the first freight order
                },
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        const freight_order_name = r.message[0].name;
                        frappe.call({
                            method: 'frappe.client.get',
                            args: {
                                doctype: 'FPL Freight Orders',
                                name: freight_order_name
                            },
                            callback: function(order_response) {
                                if (order_response.message && order_response.message.jobs) {
                                    const jobs = order_response.message.jobs;

                                    // Find the job matching job_before_cross_stuff
                                    const matching_job = jobs.find(job => job.job_name === frm.doc.job_before_cross_stuff);

                                    if (matching_job) {
                                        // Set the value of grounded_yard_location to the matching job's start_location
                                        frm.set_value('grounded_yard_location', matching_job.start_location);
                                    } else {
                                        frappe.msgprint(__('No matching job found for the selected Job Before Cross Stuff.'));
                                    }
                                }
                            }
                        });
                    }
                }
            });
        }
    },

    booking_order_id: function(frm) {
        if (frm.doc.booking_order_id) {
            frm.fields_dict['grounded_filled_containers'].grid.get_field('container_number').get_query = function(doc, cdt, cdn) {
                return {
                    query: 'cargo_management.cargo_management.doctype.perform_cross_stuff.query.get_FO_containers',
                    filters: { 
                        'booking_order_id': frm.doc.booking_order_id 
                    }
                };
            };

            frm.fields_dict['grounded_filled_containers'].grid.get_field('reference_container').get_query = function(doc, cdt, cdn) {
                return {
                    query: 'cargo_management.cargo_management.doctype.perform_cross_stuff.query.get_CFO_containers',
                    filters: { 
                        'booking_order_id': frm.doc.booking_order_id 
                    }
                };
            };
        }
        
        if (frm.doc.booking_order_id) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Booking Order',
                    name: frm.doc.booking_order_id
                },
                callback: function(r) {
                    if (r.message) {
                        var bookingOrder = r.message;
                        frm.set_value('job_before_cross_stuff', bookingOrder.location_of_cross_stuff || '');  // Assuming 'location' is the field you need
                    }
                }
            });
        }
    }
});

frappe.ui.form.on('Grounded Filled Cdt', {
    grounded_filled_containers_remove: function(frm) {
        // Recalculate total_weight and remaining_weight after a row is removed
        recalculate_total_weight(frm);
        recalculate_remaining_weight(frm);
    },
    container_number: function(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);

        if (row.container_number) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'FPL Containers',
                    filters: {
                        name: row.container_number  // Match the container number
                    },
                    fields: ['freight_order_id']
                },
                callback: function(container_response) {
                    if (container_response.message && container_response.message.length > 0) {
                        const freight_order_name = container_response.message[0].freight_order_id;
                        if (!freight_order_name) {
                            frappe.msgprint(__('The selected allocation has no linked Freight Order.'));
                            return;
                        }
                        frappe.call({
                            method: 'frappe.client.get_list',
                            args: {
                                doctype: 'FPL Freight Orders',
                                filters: {
                                    name: freight_order_name
                                },
                                fields: ['weight','bag_qty']  // Fetch the weight field
                            },
                            callback: function(weight_response) {
                                if (weight_response.message && weight_response.message.length > 0) {
                                    // Set the weight value in the row
                                    frappe.model.set_value(cdt, cdn, 'weight', weight_response.message[0].weight);
                                    frappe.model.set_value(cdt, cdn, 'fo_bags_qty', weight_response.message[0].bag_qty);
                                    // Recalculate total_weight after setting the weight
                                    recalculate_total_weight(frm);

                                    frm.refresh_field('grounded_filled_containers');
                                } else {
                                    frappe.msgprint(__('No matching weight found for the selected container.'));
                                }
                            }
                        });
                    } else {
                        frappe.msgprint(__('No matching container found for the selected container number.'));
                    }
                }
            });
        }
    },


    weight_to_transfer: function(frm) {
        // Recalculate remaining_weight when weight_to_transfer is updated
        recalculate_remaining_weight(frm);
    }
});

// Function to recalculate total_weight
function recalculate_total_weight(frm) {
    let total_weight = 0;
    const uniqueContainers = new Set(); // Track unique container numbers

    // Loop through all rows in grounded_filled_containers to calculate total weight
    frm.doc.grounded_filled_containers.forEach(row => {
        if (row.container_number && !uniqueContainers.has(row.container_number)) {
            // Add the weight only if the container_number is unique
            total_weight += row.weight || 0;
            uniqueContainers.add(row.container_number); // Mark container_number as processed
        }
    });

    // Update total_weight in the form
    frm.set_value('total_weight', total_weight);
    frm.set_value('remaining_weight', total_weight);
}


// Function to recalculate total_weight
function recalculate_remaining_weight(frm) {
    let total_weight_to_transfer = 0;

    // Loop through all rows in grounded_filled_containers to calculate total weight_to_transfer
    frm.doc.grounded_filled_containers.forEach(row => {
        total_weight_to_transfer += row.weight_to_transfer || 0; // Add weight_to_transfer if it exists, otherwise add 0
    });

    // Calculate remaining_weight as total_weight - total_weight_to_transfer
    const remaining_weight = (frm.doc.total_weight) - total_weight_to_transfer;

    // Update remaining_weight in the form
    frm.set_value('remaining_weight', remaining_weight);
}


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


