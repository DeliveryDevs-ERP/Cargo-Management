// Copyright (c) 2024, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["Train Detail"] = {
"filters": [
        {
            "fieldname": "train_no",
            "label": __("Train Number"),
            "fieldtype": "Data", 
            "default": "", 
            "reqd": 0 
        },
		{
            "fieldname": "movement",
            "label": __("Movement Type"),
            "fieldtype": "Select",
            "options": ["", "Up", "Down"], 
            "default": "", 
            "reqd": 0 
        }
    ]
};
