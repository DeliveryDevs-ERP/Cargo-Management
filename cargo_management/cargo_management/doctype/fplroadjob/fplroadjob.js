frappe.ui.form.on("FPLRoadJob", {

    before_insert: function(frm){
        populate_expenses(frm, 'Truck Job'); 
    },

    setup: function(frm) {        
        set_cost_type_filter(frm, 'Truck Job');

        // Setup for container_number_to_link field
        frm.fields_dict['container_number_to_link'].get_query = function(doc) {
            if (!frm.doc.job_type) {
                frappe.msgprint("Please specify a Job Type before selecting a container.");
                return;
            }
            return {
                query: 'cargo_management.cargo_management.doctype.fplroadjob.query.get_applicable_containers',
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

