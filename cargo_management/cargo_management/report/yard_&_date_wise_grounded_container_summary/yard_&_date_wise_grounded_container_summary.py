import frappe
from datetime import timedelta

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)

    # Generate report summary and primitive summary
    report_summary, primitive_summary = get_summary(data)

    return columns, data, None, None, report_summary, primitive_summary


def get_columns():
    """Define the columns for the report."""
    return [
        {"label": "20'", "fieldname": "twenty_feet_containers", "fieldtype": "Int", "width": 120},
        {"label": "40'", "fieldname": "forty_feet_containers", "fieldtype": "Int", "width": 120},
        {"label": "Type", "fieldname": "bo_type", "fieldtype": "Data", "width": 120},
        {"label": "Consignee", "fieldname": "consignee", "fieldtype": "Data", "width": 150},
        {"label": "Weight (MT)", "fieldname": "total_weight", "fieldtype": "Float", "width": 120},
        {"label": "Terminal", "fieldname": "terminal", "fieldtype": "Data", "width": 150},
        {"label": "BL#", "fieldname": "bill_of_landing_number", "fieldtype": "Data", "width": 150},
        {"label": "Sales Person", "fieldname": "sales_person", "fieldtype": "Data", "width": 150},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]


def get_data(filters):
    """Fetch and summarize data for the report."""
    gate_in_location = filters.get("gate_in_location") if filters else None
    filter_date = filters.get("gate_in_date") if filters else None
    data = []

    # Ensure filter_date is parsed correctly
    if filter_date:
        try:
            filter_date = frappe.utils.get_datetime(filter_date)
        except Exception as e:
            frappe.throw(f"Invalid filter date format: {e}")
    if filter_date is None or gate_in_location is None:
        return data

    # Step 1: Fetch FPLYardJobs for Gate In
    gate_in_jobs = frappe.get_all(
        "FPLYardJob",
        filters={
            "job_type": "enrhva2nvi",
            "job_start_location": gate_in_location,
            "status": "Completed",
            "gate_in": ["<=", filter_date + timedelta(days=1)]
        },
        fields=["container_number", "gate_in"]
    )

    # Step 2: Fetch container details
    containers = {}
    for job in gate_in_jobs:
        container_number = job["container_number"]
        gate_in_date = job["gate_in"].date() if job["gate_in"] else None

        if not gate_in_date:
            continue

        if gate_in_date not in containers:
            containers[gate_in_date] = {
                "twenty_feet_containers": 0,
                "forty_feet_containers": 0,
                "total_weight": 0,
                "terminal": gate_in_location,
                "rows": []
            }

        # Fetch Freight Orders for the container
        freight_order = frappe.get_value(
            "FPL Freight Orders",
            {"container_number": container_number},
            ["size", "weight", "sales_order_number", "seal_no"],
            as_dict=True
        )
        if not freight_order:
            continue

        size = freight_order["size"]
        weight = freight_order["weight"]
        sales_order = freight_order["sales_order_number"]

        # Update the size counts and weight
        if size == 20:
            containers[gate_in_date]["twenty_feet_containers"] += 1
        elif size == 40:
            containers[gate_in_date]["forty_feet_containers"] += 1
        containers[gate_in_date]["total_weight"] += weight

        # Fetch the linked Booking Order
        booking_order = frappe.get_value(
            "Booking Order",
            {"name": sales_order},
            ["bill_to", "bill_of_landing_number", "sales_person", "sales_order_type"],
            as_dict=True
        )

        consignee = booking_order["bill_to"] if booking_order else None
        bill_of_landing_number = booking_order["bill_of_landing_number"] if booking_order else None
        sales_person = booking_order["sales_person"] if booking_order else None
        bo_type = booking_order["sales_order_type"] if booking_order else None

        # Add data to the respective group
        containers[gate_in_date]["rows"].append({
            "consignee": consignee,
            "bill_of_landing_number": bill_of_landing_number,
            "sales_person": sales_person,
            "bo_type": bo_type,
            "status": "LOADED",
        })

    # Prepare final report data
    for date, details in sorted(containers.items()):
        data.append({
            "gate_in_date": date,
            "bo_type": ", ".join({row["bo_type"] for row in details["rows"] if row["bo_type"]}),
            "twenty_feet_containers": details["twenty_feet_containers"],
            "forty_feet_containers": details["forty_feet_containers"],
            "total_weight": details["total_weight"],
            "terminal": details["terminal"],
            "consignee": ", ".join({row["consignee"] for row in details["rows"] if row["consignee"]}),
            "bill_of_landing_number": ", ".join({row["bill_of_landing_number"] for row in details["rows"] if row["bill_of_landing_number"]}),
            "sales_person": ", ".join({row["sales_person"] for row in details["rows"] if row["sales_person"]}),
            "status": ", ".join({row["status"] for row in details["rows"]}),
        })

    return data


def get_summary(data):
    """Generate report_summary and primitive_summary."""
    teus = sum(
        (row["twenty_feet_containers"] * 1 + row["forty_feet_containers"] * 2)
        for row in data if "twenty_feet_containers" in row and "forty_feet_containers" in row
    )
    cntrs = sum(
        (row["twenty_feet_containers"]  + row["forty_feet_containers"])
        for row in data if "twenty_feet_containers" in row and "forty_feet_containers" in row
    )

    report_summary = [
		{"label": "Containers", "value": cntrs, "datatype": "Int"},
        {"label": "TEUS", "value": teus, "datatype": "Int"},
    ]

    primitive_summary = {
		"cntrs" : cntrs,
        "teus": teus,
    }

    return report_summary, primitive_summary
