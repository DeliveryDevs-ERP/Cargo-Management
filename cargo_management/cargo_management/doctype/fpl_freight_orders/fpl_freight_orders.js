frappe.ui.form.on("FPL Freight Orders", {


    change_container_number(frm) {
        frappe.prompt([
            {
                label: "New Container Number",
                fieldname: "container_number",
                fieldtype: "Data",
                reqd: true
            }
        ], (values) => {
            frappe.call({
                method: "cargo_management.cargo_management.doctype.fpl_freight_orders.fpl_freight_orders.change_container_number",
                args: {
                    freight_order_id: frm.doc.name,
                    new_container_number: values.container_number
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.msgprint("Container number updated successfully.");
                        frm.reload_doc();
                    }
                }
            });
        }, __("Change Container Number"), __("Update"));
    },


    after_save(frm) {
        let has_new_job = false;

        frm.doc.jobs.forEach((row) => {
            if (!row.job_id) {
                has_new_job = true;
            }
        });

        if (has_new_job) {
            frappe.call({
                method: "cargo_management.cargo_management.doctype.fpl_freight_orders.fpl_freight_orders.create_Job_withoutId",
                args: {
                    docname: frm.doc.name
                },
                callback: function () {
                    frm.refresh();
                }
            });
        }
    },

});