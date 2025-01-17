frappe.ui.form.on('Booking Order', {
    onload: function(frm) { frm.get_field('services').grid.cannot_add_rows = true; 
        frm.toggle_display('transport_type', false);
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
    },

    transport_type: function(frm) {
        frm.clear_table('services');
        frm.clear_table('miscellaneous_services');
    
        if (frm.doc.transport_type && frm.doc.sales_order_type) {
            // Fetch services based on transport type
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Service Type',
                    filters: {
                        transport_mode: frm.doc.transport_type
                    },
                    fields: ['*']
                },
                callback: function(r) {
                    if (r.message) {
                        let services = r.message;
    
                        // Fetch FPL Job Sequence to order services
                        frappe.call({
                            method: 'frappe.client.get_list',
                            args: {
                                doctype: 'FPL Jobs Sequence',
                                filters: {
                                    transport_mode: frm.doc.transport_type,
                                    sales_order_type: frm.doc.sales_order_type
                                },
                                fields: ['service_name', 'sequence'],
                                order_by: 'sequence asc'
                            },
                            callback: function(jobSeqRes) {
                                if (jobSeqRes.message) {
                                    let jobSequence = jobSeqRes.message;
    
                                    // Map services by name for easy lookup
                                    let serviceMap = {};
                                    services.forEach(service => {
                                        if (service.applicable === 0) {
                                            serviceMap[service.name] = service;
                                        }
                                    });
    
                                    // Order services based on the job sequence
                                    jobSequence.forEach(seq => {
                                        let serviceName = seq.service_name;
                                        if (serviceMap[serviceName]) {
                                            let d = frm.add_child('services');
                                            d.services = serviceMap[serviceName].name;
                                            d.service_name = serviceMap[serviceName].name1;
                                            d.applicable = 1;
                                        }
                                    });
    
                                    frm.refresh_field('services');
                                }
                            }
                        });
    
                        // Populate miscellaneous_services
                        services.forEach(service => {
                            if (service.miscellaneous === 1) {
                                let miscService = frm.add_child('miscellaneous_services');
                                miscService.services = service.name;
                                miscService.service_name = service.name1;
                                miscService.miscellaneous = 1;
                            }
                        });
    
                        frm.refresh_field('miscellaneous_services');
                    }
                }
            });
        }
    
        // toggle_columns_based_on_services(frm);

    },

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
    // qty: function(frm, cdt, cdn) {
    //     calculate_amount(frm, cdt, cdn);
    //     calculate_total(frm); // Recalculate total when qty changes
    // },
    rate: function(frm, cdt, cdn) {
        calculate_amount(frm, cdt, cdn);
        calculate_total(frm); // Recalculate total when rate changes
    },
    amount: function(frm, cdt, cdn) {
        calculate_total(frm); // Recalculate total when amount changes
    },
});

function calculate_amount(frm, cdt, cdn) {
    var child = locals[cdt][cdn];
    if (child.rate && child.rate_type == "Per Weight(Ton)") {
        var amount = child.rate * child.avg_weight * child.qty;
        frappe.model.set_value(cdt, cdn, 'amount', amount);
    }
    else if (child.rate  && child.rate_type == "Per Bag") {
        var amount = child.rate * child.bag_qty;
        frappe.model.set_value(cdt, cdn, 'amount', amount);
    }   
    else{
        var amount = child.rate * child.qty;
        frappe.model.set_value(cdt, cdn, 'amount', amount);
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
    frm.set_value('total', total);
}

