// Copyright (c) 2025, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["Booking PNL"] = {
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
            "fieldname": "transport_mode",
            "label": __("Transport Mode"),
            "fieldtype": "Link", 
			"options": "Transport Mode",
            "reqd": 1
        },
	]
};
