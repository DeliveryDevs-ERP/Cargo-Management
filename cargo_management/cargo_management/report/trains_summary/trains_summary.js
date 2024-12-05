// Copyright (c) 2024, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["Trains summary"] = {
    "filters": [
        {
            "fieldname": "train_no_from",
            "label": __("Train Number From"),
            "fieldtype": "Link", 
            "options": "FPL Perform Middle Mile", 
            "default": "", 
            "reqd": 0 
        },
        {
            "fieldname": "train_no_to",
            "label": __("Train Number To"),
            "fieldtype": "Link", 
            "options": "FPL Perform Middle Mile", 
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
