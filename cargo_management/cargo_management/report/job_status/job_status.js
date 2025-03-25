frappe.query_reports["Job Status"] = {
    "filters": [
        {
            "fieldname": "transport_mode",
            "label": __("Transport Mode"),
            "fieldtype": "Link",
            "options": "Transport Mode",
            "on_change": function() {
                var transport_mode = frappe.query_report.get_filter_value('transport_mode');
                frappe.query_report.toggle_display('check_booking', transport_mode === 'Rail (Train)');
                frappe.query_report.toggle_display('check_train', transport_mode === 'Rail (Train)');
                frappe.query_report.toggle_display('train_no', transport_mode === 'Rail (Train)' && frappe.query_report.get_filter_value('check_train'));
                frappe.query_report.toggle_display('from_date', transport_mode === 'Road (Truck)' || frappe.query_report.get_filter_value('check_booking'));
                frappe.query_report.toggle_display('to_date', transport_mode === 'Road (Truck)' || frappe.query_report.get_filter_value('check_booking'));
            }
        },
        {
            "fieldname": "check_booking",
            "label": __("Select from Bookings ?"),
            "fieldtype": "Check",
            "depends_on": "eval:doc.transport_mode=='Rail (Train)'",
            "on_change": function() {
                if (frappe.query_report.get_filter_value('check_booking')) {
                    frappe.query_report.set_filter_value('check_train', 0);
                    frappe.query_report.toggle_display('train_no', false);
                }
            }
        },
        {
            "fieldname": "check_train",
            "label": __("Select from Trains ?"),
            "fieldtype": "Check",
            "depends_on": "eval:doc.transport_mode=='Rail (Train)'",
            "on_change": function() {
                if (frappe.query_report.get_filter_value('check_train')) {
                    frappe.query_report.set_filter_value('check_booking', 0);
                    frappe.query_report.toggle_display('train_no', true);
                } else {
                    frappe.query_report.toggle_display('train_no', false);
                }
            }
        },
        {
            "fieldname": "train_nos",
            "label": __("Train Number"),
            "fieldtype": "MultiSelectList",
            "get_data": function(txt) {
                return frappe.db.get_link_options("FPL Perform Middle Mile", txt);
            },
            "depends_on": "eval:doc.check_train==1 && doc.transport_mode=='Rail (Train)'"
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Datetime",
            "default": frappe.datetime.add_months(frappe.datetime.now_datetime(), -12),
            "depends_on": "eval:doc.transport_mode=='Road (Truck)' || doc.check_booking==1"
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Datetime",
            "default": frappe.datetime.now_datetime(),
            "depends_on": "eval:doc.transport_mode=='Road (Truck)' || doc.check_booking==1"
        },
    ]
};
