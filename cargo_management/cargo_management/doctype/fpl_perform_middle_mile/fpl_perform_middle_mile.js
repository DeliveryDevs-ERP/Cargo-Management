frappe.ui.form.on("FPL Perform Middle Mile", {

    setup: function(frm) {
        frm.fields_dict['middle_mile'].grid.get_field('container').get_query = function(doc, cdt, cdn) {
            return {
                query: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.query.get_applicable_jobs',
                filters: { 
                    'container_location': frm.doc.departure_location, 
                    "container_next_location": frm.doc.arrival_location 
                }
            };
        };
    },
    
    onload: function(frm) {
        populate_expenses(frm, 'Train Job');
        frm.get_field('middle_mile_copy').grid.cannot_add_rows = true; 
        frm.get_field('middle_mile_in_loading').grid.cannot_add_rows = true; 
    },

    refresh: function(frm) {
        // Add "Receive All" button only if `finish_departure` is 1
        if (frm.doc.finish_departure == 1) {
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
            frm.set_value('finish_loading', 1);
            frm.set_value('status', "Loaded");
            frm.set_df_property("departure_tab", "hidden", false);
            console.log('Loading Completed');
            return;
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