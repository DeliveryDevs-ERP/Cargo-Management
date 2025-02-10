frappe.ui.form.on("Perform Cross Stuff", {

    before_insert: function(frm){
        populate_expenses(frm, 'Cross Stuff Job'); 
    },

    setup: function(frm) {
        set_cost_type_filter(frm, 'Cross Stuff Job');
        frm.set_query('job_before_cross_stuff', function() {
            return {
                query: 'cargo_management.cargo_management.doctype.perform_cross_stuff.query.get_unique_service_types'
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
                        name: ['like', 'FPL-FO%']
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
                    fields: ['container_number']  // Fetch the container_name
                },
                callback: function(container_response) {
                    if (container_response.message && container_response.message.length > 0) {
                        const container_name = container_response.message[0].container_number;
                        frappe.call({
                            method: 'frappe.client.get_list',
                            args: {
                                doctype: 'FPL Freight Orders',
                                filters: {
                                    container_number: container_name  // Match the container name
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
