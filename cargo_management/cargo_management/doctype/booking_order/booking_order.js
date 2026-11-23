frappe.ui.form.on('Booking Order', {
    setup(frm) {
        ['mm_loading_station', 'mm_offloading_station'].forEach(field => frm.set_query(field, () => ({
            filters: {custom_location_type: 'Yard', custom_disabled: 0},
        })));
    },
    async company(frm) { await cargo_load_services(frm); },
    onload: function(frm) { 
        
        frm.get_field('services').grid.cannot_add_rows = true; 
        frm.get_field('miscellaneous_services').grid.cannot_add_rows = true;         
        // frm.toggle_display('transport_type', false);
        frm.toggle_display('location_of_cross_stuff', false);
        frm.set_query('location_of_cross_stuff', function(doc) {
                        // Start with conditions that are always applied
                        let filters = {
                            "name1": ["in", []]
                        };
            
                        // Additional filters based on transport_type
                        if (doc.transport_type === "Rail (Train)") {
                            filters["name1"][1] = filters["name1"][1].concat(["Last Mile", "First Mile", "Middle Mile"]);
                        } else if (doc.transport_type === "Road (Truck)") {
                            filters["name1"][1] = filters["name1"][1].concat(["Long Haul", "Short Haul"]);
                        }            
                        return {
                            filters: filters
                        };
                    });
            
    },

    refresh: function(frm) {
        function update_bill_to_options() {
            var options = [];
            if (frm.doc.customer) {
                options.push(frm.doc.customer);
            }
            if (frm.doc.cargo_owner) {
                options.push(frm.doc.cargo_owner);
            }
            frm.set_df_property('bill_to', 'options', options.join('\n'));
        }

        update_bill_to_options();
        frm.fields_dict['customer'].df.onchange = update_bill_to_options;
        frm.fields_dict['cargo_owner'].df.onchange = update_bill_to_options;
        calculate_total(frm);

    },

    customer: function(frm) {
        if (frm.doc.customer) {
            frappe.call({
                method: 'cargo_management.cargo_management.doctype.booking_order.booking_order.get_sales_person',
                args: {
                    'customer': frm.doc.customer
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('sales_person', r.message);
                        frm.refresh_field('sales_person');
                    } else {
                        console.log("No Sales Person found for the selected customer.");
                        frm.set_value('sales_person', '');
                        frm.refresh_field('sales_person');
                        frappe.msgprint({
                            message: "This customer does not have a sales person tagged to it.",
                            indicator: 'orange',  
                            title: "Warning"
                        });
                    }
                }
            });
        }
    },

    sales_order_type: function(frm){
        if (frm.doc.sales_order_type){
            console.log("BO type selected ");
            frm.toggle_display('transport_type', true);
        }
        else{
            frm.toggle_display('transport_type', false);
        }
        return cargo_load_services(frm);
    },

    async transport_type(frm) { await cargo_load_services(frm); },

    fm_dropoff_location: function(frm) {
        if (frm.doc.fm_dropoff_location) {
            frm.set_value('mm_loading_station', frm.doc.fm_dropoff_location);
        }
    },

    mm_loading_station: function(frm) {
        if (frm.doc.mm_loading_station) {
            frm.set_value('fm_dropoff_location', frm.doc.mm_loading_station);
        }
    },

    mm_offloading_station: function(frm) {
        if (frm.doc.mm_offloading_station) {
            frm.set_value('lm_pickup_location', frm.doc.mm_offloading_station);
        }
    },

    lm_pickup_location: function(frm) {
        if (frm.doc.lm_pickup_location) {
            frm.set_value('mm_offloading_station', frm.doc.lm_pickup_location);
        }
    },


    lm_dropoff_location: function(frm) {
        if (frm.doc.lm_dropoff_location) {
            frm.set_value('empty_return_pickup_location', frm.doc.lm_dropoff_location);
        }
    },

});


function toggle_columns_based_on_services(frm) {
    // Iterate through the 'services' child table
    frm.doc.services.forEach(function(service) {
        if (service.service_name === "Middle Mile" && service.applicable === 0) {
            console.log("Middle Mile Unchecked !!");
            frm.toggle_display('mm_loading_station', false);
            frm.toggle_display('mm_offloading_station', false);
            frm.toggle_display('column_break_vfft', false);
        } else if (service.service_name === "Middle Mile" && service.applicable === 1) {
            frm.toggle_display('mm_loading_station', true);
            frm.toggle_display('mm_offloading_station', true);
            frm.toggle_display('column_break_vfft', true);
        }
        if (service.service_name === 'First Mile' && service.applicable === 0) {
            frm.toggle_display('fm_pickup_location', false);
            frm.toggle_display('fm_dropoff_location', false);
            frm.toggle_display('column_break_xrka', false);
        } else if (service.service_name === 'First Mile' && service.applicable === 1) {
            frm.toggle_display('fm_pickup_location', true);
            frm.toggle_display('fm_dropoff_location', true);
            frm.toggle_display('column_break_xrka', true);
        }
        if (service.service_name === 'Last Mile' && service.applicable === 0) {
            frm.toggle_display('lm_pickup_location', false);
            frm.toggle_display('lm_dropoff_location', false);
            frm.toggle_display('column_break_cmol', false);
        } else if (service.service_name === 'Last Mile' && service.applicable === 1) {
            frm.toggle_display('lm_pickup_location', true);
            frm.toggle_display('lm_dropoff_location', true);
            frm.toggle_display('column_break_cmol', true);
        }
        if (service.service_name === 'Empty Pickup' && service.applicable === 0) {
            frm.toggle_display('empty_pickup_location', false);
            frm.toggle_display('empty_pickup_dropoff_location', false);
            frm.toggle_display('column_break_hcru', false);
        } else if (service.service_name === 'Empty Pickup' && service.applicable === 1) {
            frm.toggle_display('empty_pickup_location', true);
            frm.toggle_display('empty_pickup_dropoff_location', true);
            frm.toggle_display('column_break_hcru', true);
        }
        if (service.service_name === 'Empty Return' && service.applicable === 0) {
            frm.toggle_display('empty_return_pickup_location', false);
            frm.toggle_display('empty_return_dropoff_location', false);
            frm.toggle_display('column_break_wank', false);
        } else if (service.service_name === 'Empty Return' && service.applicable === 1) {
            frm.toggle_display('empty_return_pickup_location', true);
            frm.toggle_display('empty_return_dropoff_location', true);
            frm.toggle_display('column_break_wank', true);
        }
        if (service.service_name === 'Long Haul' && service.applicable === 0) {
            frm.toggle_display('long_haul_pickup_location', false);
            frm.toggle_display('long_haul_dropoff_location', false);
            frm.toggle_display('column_break_yntn', false);
        } else if (service.service_name === 'Long Haul' && service.applicable === 1) {
            frm.toggle_display('long_haul_pickup_location', true);
            frm.toggle_display('long_haul_dropoff_location', true);
            frm.toggle_display('column_break_yntn', true);
        }
        if (service.service_name === 'Short Haul' && service.applicable === 0) {
            frm.toggle_display('short_haul_pickup_location', false);
            frm.toggle_display('short_haul_dropoff_location', false);
            frm.toggle_display('column_break_yntn', false);
        } else if (service.service_name === 'Short Haul' && service.applicable === 1) {
            frm.toggle_display('short_haul_pickup_location', true);
            frm.toggle_display('short_haul_dropoff_location', true);
            frm.toggle_display('column_break_yntn', true);
        }
    });

    // Iterate through the 'miscellaneous_services' child table
    frm.doc.miscellaneous_services.forEach(function(service) {
        if (service.service_name === 'Cross Stuff' && service.applicable === 0) {
            frm.toggle_display('location_of_cross_stuff', false);
            frm.toggle_display('column_break_yntn', false);
        } else if (service.service_name === 'Cross Stuff' && service.applicable === 1) {
            frm.toggle_display('location_of_cross_stuff', true);
            frm.toggle_display('column_break_yntn', true);
        }
    });
}


frappe.ui.form.on('FPL Servicess', {
    applicable: function(frm, cdt, cdn) {
        toggle_columns_based_on_services(frm);
    }
});



frappe.ui.form.on('Cargo Detail cdt', {
    avg_weight: async function(frm, cdt, cdn) {
        await validate_weight(frm, cdt, cdn);
        if (locals[cdt][cdn].rate_type === "Per Weight(Ton)") {
            return recalculate_cargo_amount(frm, cdt, cdn);
        }
    },
    rate: function(frm, cdt, cdn) {
        return recalculate_cargo_amount(frm, cdt, cdn);
    },
    rate_type: function(frm, cdt, cdn) {
        return recalculate_cargo_amount(frm, cdt, cdn);
    },
    qty: function(frm, cdt, cdn) {
        if (locals[cdt][cdn].rate_type !== "Per Bag") {
            return recalculate_cargo_amount(frm, cdt, cdn);
        }
    },
    bag_qty: function(frm, cdt, cdn) {
        if (locals[cdt][cdn].rate_type === "Per Bag") {
            return recalculate_cargo_amount(frm, cdt, cdn);
        }
    },
    amount: function(frm, cdt, cdn) {
        return calculate_total(frm); // Preserve manual Amount edits.
    },
    cargo_details_add: function(frm) {
        return calculate_total(frm);
    },
    cargo_details_remove: function(frm) {
        return calculate_total(frm);
    },
});

async function recalculate_cargo_amount(frm, cdt, cdn) {
    await calculate_amount(frm, cdt, cdn);
    return calculate_total(frm);
}

function calculate_amount(frm, cdt, cdn) {
    var child = locals[cdt][cdn];
    if (child.rate && child.rate_type == "Per Weight(Ton)") {
        var amount = child.rate * child.avg_weight * child.qty;
        return frappe.model.set_value(cdt, cdn, 'amount', amount);
    }
    else if (child.rate  && child.rate_type == "Per Bag") {
        var amount = child.rate * child.bag_qty;
        return frappe.model.set_value(cdt, cdn, 'amount', amount);
    }   
    else{
        var amount = child.rate * child.qty;
        return frappe.model.set_value(cdt, cdn, 'amount', amount);
    }
}


function calculate_total(frm) {
    let total = 0;

    // Iterate through the child table rows and sum up the 'amount' field
    frm.doc.cargo_details.forEach(function(row) {
        if (row.amount) {
            total += flt(row.amount);
        }
    });

    // Update the 'total' field in the parent form
    return frm.set_value('total', total);
}

function validate_weight(frm, cdt, cdn) {
    var child = locals[cdt][cdn];

    // Check if size is defined before making a database call
    if (child.size) {
        // Fetch container types with the same size as the child row
        return frappe.db.get_list('Container Type', {
            fields: ['name', 'size', 'max_cargo_weight_kg'],
            filters: {
                'size': child.size
            }
        }).then(containers => {
            if (containers && containers.length > 0) {
                // Assume the first matched container type is the relevant one
                containers.sort((a, b) => b.max_cargo_weight_kg - a.max_cargo_weight_kg);

                // Use the container with the highest max_cargo_weight_kg
                let container = containers[0];
                
                if (child.avg_weight > container.max_cargo_weight_kg) {
                    // If the weight is greater than the max cargo weight, warn the user
                    frappe.msgprint(__('The weight entered exceeds the maximum limit for the selected container size.'));
                    return frappe.model.set_value(cdt, cdn, 'avg_weight', 0);
                }
            } else {
                // If no container type matches the size
                frappe.msgprint(__('No container found with the specified size.'));
            }
        }).catch(err => {
            console.error('Error fetching container types:', err);
            frappe.msgprint(__('Failed to validate weight.'));
        });
    } else {
        // If size is not defined in the child row
        frappe.msgprint(__('Please enter the size of the cargo first.'));
    }
}

// Server-derived Company catalogs and a request identity prevent stale async
// replies from repopulating the wrong movement/profile.
async function cargo_load_services(frm) {
    if (frm.doc.docstatus || !frm.doc.company || !frm.doc.transport_type || !frm.doc.sales_order_type) return;
    const key = JSON.stringify([frm.doc.company, frm.doc.transport_type, frm.doc.sales_order_type]);
    const serial = frm.__cargo_catalog_serial = (frm.__cargo_catalog_serial || 0) + 1;
    const response = await frm.call('get_service_catalog');
    if (serial !== frm.__cargo_catalog_serial || key !== JSON.stringify([frm.doc.company, frm.doc.transport_type, frm.doc.sales_order_type])) return;
    const scope = response.message;
    const services = Object.fromEntries(scope.services.map(row => [row.name, row]));
    frm.clear_table('services'); frm.clear_table('miscellaneous_services');
    scope.sequence.forEach(row => {
        const service = services[row.service_name];
        if (!service) return;
        Object.assign(frm.add_child('services'), {services: service.name, service_name: service.name1, applicable: 1});
    });
    scope.services.filter(row => row.miscellaneous).forEach(service => {
        Object.assign(frm.add_child('miscellaneous_services'), {services: service.name, service_name: service.name1, miscellaneous: 1});
    });
    frm.refresh_field('services'); frm.refresh_field('miscellaneous_services');
}
