// Copyright (c) 2025, Osama and contributors
// For license information, please see license.txt

frappe.query_reports["Last Mile with Rail No"] = {
"filters": [
        {
            "fieldname":"status",
            "label": __("Status"),
            "fieldtype": "Select",
            "options": "Assigned",
            "default": "Assigned"
        },
        {
            "fieldname":"job_name",
            "label": __("Job Name"),
            "fieldtype": "Select",
            "options": "Last Mile",
            "default": "Last Mile"
        }
    ]
};

