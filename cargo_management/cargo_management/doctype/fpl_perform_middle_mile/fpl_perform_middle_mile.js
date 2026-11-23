frappe.ui.form.on("FPL Perform Middle Mile", {

    // before_insert: function(frm){
    //     populate_expenses(frm, 'Train Job');
    // },


    setup: function(frm) {
        ['departure_location', 'arrival_location'].forEach(field => frm.set_query(field, () => ({
            filters: {custom_location_type: 'Yard', custom_disabled: 0},
        })));

        set_container_name_filter(frm);
        set_container_filter(frm);
    },
    
    onload: async function(frm) {
        frm.get_field('middle_mile').grid.cannot_add_rows = true; 
        frm.get_field('middle_mile_copy').grid.cannot_add_rows = true; 
        frm.get_field('middle_mile_in_loading').grid.cannot_add_rows = true; 
        await set_train_company_context(frm);
    },

    company: async function(frm) {
        await set_cost_type_filter(frm, 'Train Job');
    },

    async cancel_loading(frm) {
        if (frm.is_dirty()) {
            frappe.throw(__('Save or reload the train before reversing its operational phase.'));
        }
        await frappe.call({
            method: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.fpl_perform_middle_mile.cancel_loading',
            args: {docname: frm.doc.name},
            freeze: true
        });
        await frm.reload_doc();
    },

    cancel_formation(frm){
        frm.clear_table("middle_mile");
        frm.set_value('finish_train_formation', 0);
        frm.set_value('status', "");
        frm.refresh_field("wagons");
    },

    fetch_wagons_from_train(frm){
        frappe.prompt(
            {
                label: __("Please Specify Train Number"),
                fieldname: "train_number",
                fieldtype: "Link",
                options: "FPL Perform Middle Mile", // Assuming 'Train' is a DocType that contains details about trains
                get_query: () => ({
                    filters: {
                        status: "Arrived", // Only fetch trains that have arrived
                    },
                }),
            },
            (values) => {
                // Make server call to fetch wagons from the specified train
                frappe.call({
                    method: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.query.get_wagons_from_train',
                    args: {
                        train_number: values.train_number
                    },
                    callback: function(r) {
                        if(r.message) {
                            // Clear existing wagons
                            frm.clear_table('wagons');
                            // Add fetched wagons to the wagons table
                            r.message.forEach(function(wagon) {
                                var row = frm.add_child('wagons');
                                row.wagon_number = wagon.wagon_number;
                                row.wagon_type = wagon.wagon_type;
                                row.loaded_ = 0;
                            });
                            frm.refresh_field('wagons');
                        }
                    }
                });
            },
            __("Fetch Wagons")
        );
    },


    async cancel_departure(frm) {
        if (frm.is_dirty()) {
            frappe.throw(__('Save or reload the train before reversing its operational phase.'));
        }
        await frappe.call({
            method: 'cargo_management.cargo_management.doctype.fpl_perform_middle_mile.fpl_perform_middle_mile.cancel_departure',
            args: {docname: frm.doc.name},
            freeze: true
        });
        await frm.reload_doc();
    },

    depart_all(frm){
                        frm.doc.middle_mile_in_loading.forEach(row => {
                    row.departed_ = 1;
                });
                if (frm.doc.middle_mile_in_loading.length) frm.dirty();
                frm.refresh_field("middle_mile_in_loading");
    },

    refresh: function(frm) {
        // A native save changes __islocal without another onload event.
        if (frm._cargo_company_context) present_train_company(frm);
        
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

                            // Retain current allocations. Clearing them after building
                            // the exclusion sets loses selections on a repeated fetch.
                            // Add only newly fetched wagon/container identities.
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
                if (frm.doc.middle_mile_copy.length) frm.dirty();
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

    async before_save(frm) {
        // Each save advances at most one phase, using the actual unsaved grid.
        // The server validates allocations, weights, permissions and history.
        if (!frm.doc.finish_train_formation) {
            await frm.set_value({finish_train_formation: 1, status: 'Train Formed'});
        } else if (!frm.doc.finish_loading && frm.doc.loading_time && frm.doc.loading_end_time) {
            if (!(frm.doc.middle_mile || []).some(row => row.container)) {
                frappe.throw(__('Allocate a container before finishing loading.'));
            }
            await frm.set_value({finish_loading: 1, status: 'Loaded'});
        } else if (!frm.doc.finish_departure && frm.doc.finish_loading && frm.doc.departure_time) {
            if (!validate_depart_tick(frm)) frappe.throw(__('Select at least one container to depart.'));
            await frm.set_value({finish_departure: 1, status: 'Departed'});
        } else if (!frm.doc.finish_arrival && frm.doc.finish_departure && frm.doc.actual_arrival_datetime) {
            if (!(frm.doc.middle_mile_copy || []).some(row => row.received_)) {
                frappe.throw(__('Select at least one received container before finishing arrival.'));
            }
            await new Promise((resolve, reject) => frappe.confirm(
                __('Complete arrival for the selected received containers? Charges will be retained as financial history.'),
                resolve, () => reject(new Error(__('Arrival confirmation cancelled.')))
            ));
            await frm.set_value({finish_arrival: 1, status: 'Arrived'});
        }
    }
});


frappe.ui.form.on("FPL MM cdt", {
    job: update_related_tables,
    mm_job_id: update_related_tables,
    wagon_number: update_related_tables,
    container(frm, cdt, cdn) {
        update_related_tables(frm, cdt, cdn);
        set_container_filter(frm);
    },
    fo: function(frm, cdt, cdn) {
        Fetch_size(frm, cdt, cdn);
        Fetch_weight(frm, cdt, cdn);
    }
});


function update_related_tables(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    // An unset identity is not a match for another unallocated grid row.
    if (!row.mm_job_id) return;
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

async function set_train_company_context(frm) {
    const documentName = frm.doc.name;
    if (frm._cargo_company_document !== documentName) {
        frm._cargo_company_document = documentName;
    }
    const initialCompany = frm.doc.company;
    const response = await frappe.call({
        method: 'cargo_management.cargo_management.utils.configuration.get_train_company_context'
    });
    if (frm.doc.name !== documentName) return;
    frm._cargo_company_context = response.message || {companies: []};
    const companies = frm._cargo_company_context.companies;
    frm.set_query('company', () => ({filters: {name: ['in', companies]}}));
    if (frm.is_new() && frm.doc.company === initialCompany) {
        const soleCompany = frm._cargo_company_context.sole_company;
        const explicitCompany = frappe.route_options?.company;
        const company = soleCompany || (companies.includes(explicitCompany) ? explicitCompany : null);
        frm._cargo_company_setting_context = true;
        try {
            if ((frm.doc.company || null) !== company) await frm.set_value('company', company);
        } finally {
            frm._cargo_company_setting_context = false;
        }
    }
    present_train_company(frm);
}

function present_train_company(frm) {
    const canChoose = frm.is_new() && (frm._cargo_company_context.companies || []).length > 1;
    // A read-only Link provides compact context without an editable selector.
    frm.set_df_property('company', 'read_only', !canChoose);
    frm.set_df_property('company', 'reqd', frm.is_new());
}


function set_container_name_filter(frm) {
    frm.fields_dict['expenses'].grid.get_field('container_number').get_query = function() {
        const receivedAllocations = (frm.doc.middle_mile_copy || [])
            .filter(row => row.received_ === 1 && row.container)
            .map(row => row.container);
        return {
            filters: {
                'name': ['in', receivedAllocations]
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
    frm.fields_dict['middle_mile'].grid.get_field('container').get_query = function(doc, cdt, cdn) {
        // v16 validates the selected Link against this query as well as using
        // it for autocomplete. Exclude other rows, never the current selection.
        const existingContainers = (frm.doc.middle_mile || [])
            .filter(row => row.name !== cdn && row.container)
            .map(row => row.container);
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
    if (row.purchase_invoice_no || row.sales_invoice_no) frappe.throw(__('Financially referenced Cargo expenses must be retained. Invoices are never deleted automatically.'));
},

    expenses_move: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log("Attempting to Move row:", row);
        frm.save();
    }
});



function validate_depart_tick(frm) {
    let hasDeparted = false; // Flag to track if any row has departed

    // Loop through each row in the child table
    $.each(frm.doc.middle_mile_in_loading || [], function(i, row) {
        if(row.departed_ === 1) {
            hasDeparted = true;
            return false; // Exit the loop early as we found a match
        }
    });

    return hasDeparted;
}


function validate_arrival_tick(frm) {
    let hasArrived = false; // Flag to track if any row has departed

    // Loop through each row in the child table
    $.each(frm.doc.middle_mile_copy || [], function(i, row) {
        if(row.received_ === 1) {
            hasArrived = true;
            return false; 
        }
    });

    if (hasArrived) {
        frm.set_value('finish_arrival', 1);
        frm.set_value('status', "Arrived");
        frm.refresh_field('wagons');
        frm.save();
    }
    else {
        frappe.msgprint({
                             title: 'Arrival Tick Error',
                            message: 'Unable to complete Arrival as the none of the containers are selected to receive.',
                             indicator: 'red'
                         });
    }
}
