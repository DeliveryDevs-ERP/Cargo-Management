frappe.ui.form.on("FPL Freight Orders", {
    after_save(frm) {
        let has_new_job = false;

        frm.doc.jobs.forEach((row) => {
            if (!row.job_id) {  // Check if any job row has no job_id
                has_new_job = true;
            }
        });

        if (has_new_job) {
            frappe.call({
                method: "cargo_management.cargo_management.doctype.fpl_freight_orders.fpl_freight_orders.create_Job_withoutId",
                args: {
                    docname: frm.doc.name
                },
                callback: function() {
					frm.refresh();
				}
            });
        }
    }
});
