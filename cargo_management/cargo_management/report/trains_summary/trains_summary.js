// Copyright (c) 2024, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["Trains summary"] = {
    "filters": [
        {
            "fieldname": "train_no_from",
            "label": __("Departure Date From"),
            "fieldtype": "Datetime", 
            "default": frappe.datetime.add_months(frappe.datetime.now_datetime(), -12), 
            "reqd": 0 
        },
        {
            "fieldname": "train_no_to",
            "label": __("Departure Date Till"),
            "fieldtype": "Datetime", 
            "default": frappe.datetime.now_datetime(), 
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
