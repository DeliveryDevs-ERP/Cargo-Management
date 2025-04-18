// Copyright (c) 2025, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["RAIL PNL NEW"] = {
	"filters": [
		{
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Datetime", 
            "default": frappe.datetime.add_months(frappe.datetime.now_datetime(), -12), 
            "reqd": 0 
        },
        {
            "fieldname": "to_date",
            "label": __("to Date"),
            "fieldtype": "Datetime", 
            "default": frappe.datetime.now_datetime(), 
            "reqd": 0 
        },
        {
            "fieldname": "train_nos",
            "label": __("Train Number"),
            "fieldtype": "MultiSelectList",
            "get_data": function(txt) {
                return frappe.db.get_link_options("FPL Perform Middle Mile", txt);
            }
        },
	]
};
