// Copyright (c) 2024, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["Yard & Date wise Grounded Container Summary"] = {
"filters": [
        {
            "fieldname": "gate_in_location",
            "label": __("Grounded Location"),
            "fieldtype": "Link",
            "options": "Location", // Link to Location doctype
            "get_query": function() {
                return {
                    filters: {
                        location_type: "Yard" // Only fetch locations of type 'Yard'
                    }
                };
            },
            "default": "", // No default value
            "reqd": 0 // Not required
        },
        {
            "fieldname": "gate_in_date",
            "label": __("Grounded Date"),
            "fieldtype": "Date", // Date field for filtering by grounding date
            "default": "", // No default value
            "reqd": 0 // Not required
        }
    ]
};
