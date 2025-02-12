frappe.ui.form.on("FPL Perform Middle Mile", {

    // before_insert: function(frm){
    //     populate_expenses(frm, 'Train Job');
    // },


    setup: function(frm) {
        set_container_name_filter(frm);
        set_container_filter(frm);
    },
    
    onload: function(frm) {
        frm.get_field('middle_mile').grid.cannot_add_rows = true; 
        frm.get_field('middle_mile_copy').grid.cannot_add_rows = true; 
        frm.get_field('middle_mile_in_loading').grid.cannot_add_rows = true; 
    },

    cancel_loading(frm){
        frm.clear_table("middle_mile_in_loading");
        frm.set_value('finish_loading', 0);
        frm.set_value('status', "Train Formed");
        frm.refresh_field("middle_mile_in_loading");
    },

    depart_all(frm){
                        frm.doc.middle_mile_in_loading.forEach(row => {
                    row.departed_ = 1;
                });
                frm.refresh_field("middle_mile_in_loading");
    },

    refresh: function(frm) {
        
        if (frm.doc.finish_train_formation == 0) {
            frm.add_custom_button(__('Fetch Wagons from Undeparted Trains'), function() {


                if (frm.doc.movement_type && frm.doc.departure_location){
                    // Make the frappe.call to the Python function
                frappe.call({
                    method: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.query.fetch_wagons_from_undeparted_trains',
                    args: {
                        departure_location: frm.doc.departure_location,
                        movement_type: frm.doc.movement_type
                    },
                    callback: function(r) {
                        if (r.message) {
                            // Prepare to track existing wagon numbers
                            let existingWagons = {};
                            let existingContainers = {};
                            frm.doc.wagons.forEach(function(w) {
                                existingWagons[w.wagon_number] = true;
                            });

                            frm.doc.middle_mile.forEach(function(m) {
                                existingContainers[m.container] = true; 
                            });

                            // Clear the existing rows in the wagons table
                            frm.clear_table('wagons');
                            frm.clear_table('middle_mile');

                            // Add new rows based on the fetched data, ensuring they are distinct
                            r.message.forEach(function(wagon) {
                                if (!existingWagons[wagon.wagon_number]) {
                                    var row = frm.add_child('wagons');
                                    row.wagon_number = wagon.wagon_number;
                                    row.wagon_type = wagon.wagon_type;
                                    row.loaded_ = 1;
                                    existingWagons[wagon.wagon_number] = true; 
                                }

                                // Check if the container has already been added
                                if (!existingContainers[wagon.container]) {
                                    var row2 = frm.add_child('middle_mile');
                                    row2.wagon_number = wagon.wagon_number;
                                    row2.container = wagon.container;
                                    row2.size = wagon.size;
                                    row2.weight = wagon.weight;
                                    row2.loaded_ = 1;      
                                    row2.departed_ = 0;
                                    existingContainers[wagon.container] = true; 
                                }
                            });

                            // Refresh the child table to show new data
                            frm.refresh_field('wagons');
                            frm.refresh_field('middle_mile');

                                }
                            }
                        });
                }
                else {
                    if (!frm.doc.departure_location && !frm.doc.movement_type) {
                        frappe.msgprint(__('Please specify both the departure location and the movement type.'));
                    } else if (!frm.doc.departure_location) {
                        frappe.msgprint(__('Missing departure location.'));
                    } else if (!frm.doc.movement_type) {
                        frappe.msgprint(__('Missing movement type.'));
                    }
                }
                
                
            });
        }
       
        if (frm.doc.finish_departure == 1 && frm.doc.finish_arrival == 0) {
            frm.add_custom_button(__('Receive All'), function() {
                frm.doc.middle_mile_copy.forEach(row => {
                    row.received_ = 1;
                });
                frm.refresh_field("middle_mile_copy");
            });
        }


        set_cost_type_filter(frm, 'Train Job');

        frm.fields_dict['middle_mile_in_loading'].grid.get_field('container').get_query = function(doc, cdt, cdn) {
            return {
                query: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.query.get_containers_from_Loading',
                filters: { 
                    'parent': frm.doc.name, 
                }
            };
        };

        frm.fields_dict['middle_mile_copy'].grid.get_field('container').get_query = function(doc, cdt, cdn) {
            return {
                query: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.query.get_containers_from_Loading',
                filters: { 
                    'parent': frm.doc.name, 
                }
            };
        };

    },

    departure_location(frm) {
        console.log('Trigger on departure_location change:', frm.doc.departure_location);
        frm.refresh_field('middle_mile');
    },


    // rail_number(frm) {
    //     frm.doc.rail_number_state = frm.doc.rail_number;
    //     // frm.trigger("update_middle_mile_jobs");
    // },

    // movement_type(frm) {
    //     frm.doc.movement_type_state = frm.doc.movement_type;
    //     // frm.trigger("update_middle_mile_jobs");
    // },

    // update_middle_mile_jobs(frm) {
    //     if (frm.doc.rail_number_state || frm.doc.movement_type) {
    //         frappe.call({
    //             method: "frappe.client.get_list",
    //             args: {
    //                 doctype: "FPLRailJob",
    //                 filters: {
    //                     sales_order_number: frm.doc.sales_order_number
    //                 },
    //                 fields: ["name"]
    //             },
    //             callback: function(r) {
    //                 if (r.message) {
    //                     r.message.forEach(job => {
    //                         frappe.call({
    //                             method: "frappe.client.set_value",
    //                             args: {
    //                                 doctype: "FPLRailJob",
    //                                 name: job.name,
    //                                 fieldname: {
    //                                     rail_number: frm.doc.rail_number_state,
    //                                     rail_movement_type: frm.doc.movement_type_state
    //                                 }
    //                             },
    //                             callback: function(response) {
    //                                 console.log("Updated job:", response);
    //                             }
    //                         });
    //                     });
    //                 }
    //             }
    //         });
    //     }
    // },

    before_save(frm) {
        console.log('Before Save Triggered');
        console.log('Finish Train Formation:', frm.doc.finish_train_formation);
        console.log('Finish Loading:', frm.doc.finish_loading);
        console.log('Finish Departure:',frm.doc.finish_departure);

        if (frm.doc.finish_train_formation == 1 && frm.doc.finish_loading == 1 && frm.doc.finish_departure == 1 && frm.doc.finish_arrival == 0) {
            frm.set_value('finish_arrival', 1);
            frm.set_value('status', "Arrived");
            console.log('Arrival Completed');
            return;
        }

        if (frm.doc.finish_train_formation == 1 && frm.doc.finish_loading == 1 && frm.doc.finish_departure == 0) {
            frm.set_value('finish_departure', 1);
            frm.set_value('status', "Departed");
            frm.set_df_property("tab_5_tab", "hidden", false);
            console.log('Departure Completed');
            return;
        }

        if (frm.doc.finish_train_formation == 1 && frm.doc.finish_loading == 0) {
            frappe.call({
                method: "cargo_management.cargo_management.doctype.fpl_perform_middle_mile.fpl_perform_middle_mile.validate_weight_Loading",
                args: {
                    docname: frm.doc.name
                },
                callback: function(r) {
                    if (r.message === true) {
                        frm.set_value('finish_loading', 1);
                        frm.set_value('status', "Loaded");
                        frm.set_df_property("departure_tab", "hidden", false);
                        console.log('Loading Completed');
                    }else{
                        frappe.msgprint({
                            title: 'Loading Weight Error',
                            message: 'Unable to complete loading as the weight exceeds the maximum limit.',
                            indicator: 'red'
                        });
                    }
                }
            });
        }
        
        if (frm.doc.finish_train_formation == 0) {
            frm.set_value('finish_train_formation', 1);
            frm.set_value('status', "Train Formed");
            frm.set_df_property("loading_tab", "hidden", false);
            console.log('Train Formation Completed');
            return;
        }
        
    }
});


frappe.ui.form.on("FPL MM cdt", {
    job: update_related_tables,
    mm_job_id: update_related_tables,
    wagon_number: update_related_tables,
    container: update_related_tables,
    container: set_container_filter,
    fo: function(frm, cdt, cdn) {
        Fetch_size(frm, cdt, cdn);
        Fetch_weight(frm, cdt, cdn);
    }
});


function update_related_tables(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    frm.doc.middle_mile_in_loading.forEach((in_loading_row) => {
        if (in_loading_row.mm_job_id === row.mm_job_id) {
            if (row.fieldname !== 'received_') {
                in_loading_row.job = row.job;
                in_loading_row.mm_job_id = row.mm_job_id;
                in_loading_row.wagon_number = row.wagon_number;
                in_loading_row.container = row.container;
            }
        }
    });

    frm.doc.middle_mile_copy.forEach((copy_row) => {
        if (copy_row.mm_job_id === row.mm_job_id) {
            if (row.fieldname !== 'received_') {
                copy_row.job = row.job;
                copy_row.mm_job_id = row.mm_job_id;
                copy_row.wagon_number = row.wagon_number;
                copy_row.container = row.container;
            }
        }
    });

    frm.refresh_field("middle_mile_in_loading");
    frm.refresh_field("middle_mile_copy");
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
    let containersInCopy = frm.doc.middle_mile_copy
        .filter(row => row.received_ === 1)
        .map(row => row.container_number);

    frm.fields_dict['expenses'].grid.get_field('container_number').get_query = function() {
        return {
            filters: {
                'container_number': ['in', containersInCopy]
            }
        };
    };
}

function Fetch_size(frm, cdt, cdn) {
    let row = locals[cdt][cdn];  // Get the current row in the child table
        frappe.db.get_value('FPL Freight Orders', { 'name': row.fo }, 'size')
            .then(r => {
                if (r.message) {
                    // If a size value is found, set it in the child table's size field
                    frappe.model.set_value(cdt, cdn, 'size', r.message.size);
                    frm.refresh_field("middle_mile_in_loading");
                }
            });
}


function Fetch_weight(frm, cdt, cdn) {
    let row = locals[cdt][cdn];  // Get the current row in the child table
        frappe.db.get_value('FPL Freight Orders', { 'name': row.fo }, 'weight')
            .then(r => {
                if (r.message) {
                    // If a size value is found, set it in the child table's size field
                    frappe.model.set_value(cdt, cdn, 'weight', r.message.weight);
                    frm.refresh_field("middle_mile_in_loading");
                }
            });
}


function set_container_filter(frm) {
    let existingContainers = [];
    frm.doc.middle_mile.forEach(function(row) {
        if (row.container) {
            existingContainers.push(row.container);
        }
    });
    console.log("existingContainers ", existingContainers);
    frm.fields_dict['middle_mile'].grid.get_field('container').get_query = function(doc, cdt, cdn) {
        return {
            query: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.query.get_applicable_jobs',
            filters: { 
                'container_location': frm.doc.departure_location, 
                "container_next_location": frm.doc.arrival_location,
                "not_in_container": existingContainers
            }
        };
    };
}

// Utility function to toggle read-only status
// function toggle_read_only_for_container(frm) {
//     const rows = frm.doc.middle_mile_in_loading || [];
//     rows.forEach(function(row) {
//         // Check if loaded_ is 1 and then set read-only
//         let readOnly = row.loaded_ === 1;
//         console.log("Read only value ? ",readOnly);
//         // console.log("cont 1",frm.fields_dict['middle_mile_in_loading'].grid)
//         // console.log("cont 2",frm.fields_dict['middle_mile_in_loading'].grid.fields_map.container)
//         frm.fields_dict['middle_mile_in_loading'].grid.fields_map['container'].grid.set_df_property('container', 'read_only', readOnly, row.name);
//     });
//     // frm.refresh_field('middle_mile_in_loading');
// }

frappe.ui.form.on('Expenses cdt', {
    before_expenses_remove: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log("Attempting to delete row:", row);

        if (row.purchase_invoice_no) {
            frappe.db.get_doc("Purchase Invoice", row.purchase_invoice_no)
                .then(PI => {
                    console.log("Fetched PI:", PI);
                    if (PI.docstatus === 0) {
                        // If the PI is in draft status, allow deletion
                        frappe.db.delete_doc('Purchase Invoice', PI.name)
                            .then(() => {
                                frm.save_or_update();
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
    }
});

