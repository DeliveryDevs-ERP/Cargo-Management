// Copyright (c) 2024, Osama and contributors
// For license information, please see license.txt

frappe.ui.form.on("FPLRailJob", {
    refresh(frm) {
        // Add any initialization code here if needed
    },
    
    train_number: function(frm) {
        // Check if the train_number has been entered
        if (frm.doc.train_number) {
            // Save the form automatically
            frm.save();
        }
    }
});
