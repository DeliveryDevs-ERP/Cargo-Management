import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)

    # Generate report summary and primitive summary
    report_summary, primitive_summary = get_report_summary(data, filters)

    return columns, data, None, None, report_summary, primitive_summary


def get_columns():
    """Define the columns for the report."""
    return [
        # {"label": "S.No", "fieldname": "s_no", "fieldtype": "Int", "width": 50},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data", "width": 80},
        {"label": "CONT #", "fieldname": "container_no", "fieldtype": "Data", "width": 150},
        {"label": "WT/MT", "fieldname": "weight", "fieldtype": "Data", "width": 100},
        {"label": "Seal#", "fieldname": "seal_no", "fieldtype": "Data", "width": 120},
        {"label": "Shipping Line", "fieldname": "shipping_line", "fieldtype": "Data", "width": 150},
        {"label": "Wagon No", "fieldname": "wagon_no", "fieldtype": "Data", "width": 120},
        {"label": "CNEE", "fieldname": "consignee", "fieldtype": "Data", "width": 150},
        {"label": "BL#", "fieldname": "bill_of_landing_number", "fieldtype": "Data", "width": 150},
        {"label": "POD", "fieldname": "pod", "fieldtype": "Data", "width": 150},
        {"label": "Sales Person", "fieldname": "sales_person", "fieldtype": "Data", "width": 150},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},  # Added Status column
        {"label": "Cntr Grounded @ JMTH (Date/Time)", "fieldname": "grounded_datetime", "fieldtype": "Datetime", "width": 200},
    ]


def get_data(filters):
    """Fetch and process data for the report."""
    train_no = filters.get("train_no") if filters else None
    movement_type = filters.get("movement") if filters else None

    data = []

    # Step 1: Fetch a single FPL Perform Middle Mile doc based on filters
    train_doc = frappe.get_value(
        "FPL Perform Middle Mile",
        {"rail_number": train_no, "movement_type": movement_type} if train_no or movement_type else {},
        "*",
        as_dict=True
    )

    if not train_doc:
        frappe.errprint("No Train Document found with the given filters.")
        return data

    frappe.errprint(f"Fetched Train Doc: {train_doc}")

    # Step 2: Fetch container and wagon data
    container_data = frappe.get_all(
        "FPL MM cdt",
        filters={"parent": train_doc["name"]},
        fields=["container_number", "wagon_number", "received_"]
    )

    frappe.errprint(f"Fetched Container Data: {container_data}")

    # Step 3: Filter unique containers and wagons, prioritize received_
    unique_data = {}
    for row in container_data:
        container_number = row["container_number"]
        wagon_number = row["wagon_number"]
        received = row["received_"]

        if container_number and wagon_number:  # Exclude rows with None values
            if container_number not in unique_data or received == 1:
                unique_data[container_number] = {
                    "wagon_number": wagon_number,
                    "received_": received,
                }

    frappe.errprint(f"Filtered Unique Data: {unique_data}")

    # Step 4: Fetch data for valid containers
    for container_number, details in unique_data.items():
        wagon_number = details["wagon_number"]
        received = details["received_"]

        # Fetch Freight Orders linked to the container
        freight_orders = frappe.get_all(
            "FPL Freight Orders",
            filters={"container_number": container_number},
            fields=["name", "size", "weight", "seal_no", "sales_order_number"]
        )

        if not freight_orders:
            continue
        fo = freight_orders[0]

        # Fetch the linked Booking Order
        booking_order = frappe.get_value(
            "Booking Order",
            {"name": fo["sales_order_number"]},
            ["shipping_line", "bill_to", "bill_of_landing_number", "sales_person"],
            as_dict=True
        )

        # Fetch POD from the first job in the FO's jobs child table
        job_data = frappe.get_all(
            "FPL Jobs",
            filters={"parent": fo["name"]},
            fields=["start_location"],
            order_by="idx asc",  # Ensure the first job is fetched
            limit=1
        )
        pod = job_data[0]["start_location"] if job_data else None

        # Determine container status
        if train_doc["status"] == "Loaded":
            container_status = "Loaded"
        elif train_doc["status"] == "Departed":
            container_status = "In-transit"
        elif train_doc["status"] == "Arrived":
            container_status = "Received" if received == 1 else "Not Received"
        else:
            container_status = "Unknown"

        # Add data row
        data.append({
            "container_no": container_number,
            "size": fo["size"],
            "weight": fo["weight"],
            "seal_no": fo["seal_no"],
            "shipping_line": booking_order["shipping_line"] if booking_order else None,
            "wagon_no": wagon_number,
            "consignee": booking_order["bill_to"] if booking_order else None,
            "bill_of_landing_number": booking_order["bill_of_landing_number"] if booking_order else None,
            "pod": pod,
            "sales_person": booking_order["sales_person"] if booking_order else None,
            "status": container_status,
            "grounded_datetime": frappe.get_last_doc("FPLYardJob", filters={"job_type": "enrhva2nvi", "status": "Completed", "container_number": container_number}).gate_in,
        })

    return data


def get_report_summary(data, filters):
    """Generate report summary and primitive summary."""
    total_containers = len(data)
    loaded = sum(1 for row in data if row["status"] == "Loaded")
    in_transit = sum(1 for row in data if row["status"] == "In-transit")
    received = sum(1 for row in data if row["status"] == "Received")
    not_received = sum(1 for row in data if row["status"] == "Not Received")

    # Fetch train document details
    train_doc = frappe.get_value(
        "FPL Perform Middle Mile",
        {"rail_number": filters.get("train_no"), "movement_type": filters.get("movement")},
        ["departure_location", "arrival_location", "loco_number", "break_number", "departure_time", "actual_arrival_datetime","status"],
        as_dict=True
    )

    # Add train-specific details to the summary
    report_summary = [
        {"label": "Total Containers", "value": total_containers},
        {"label": "Loaded", "value": loaded},
        {"label": "In-transit", "value": in_transit},
        {"label": "Received", "value": received},
        {"label": "Not Received", "value": not_received},
        {"label": "Departure Location", "value": train_doc.get("departure_location") if train_doc else None},
        {"label": "Arrival Location", "value": train_doc.get("arrival_location") if train_doc else None},
        {"label": "Engine Number", "value": train_doc.get("loco_number") if train_doc else None},
        {"label": "Break Number", "value": train_doc.get("break_number") if train_doc else None},
        {"label": "Departure Time", "value": train_doc.get("departure_time") if train_doc else None},
        {"label": "Arrival Time", "value": train_doc.get("actual_arrival_datetime") if train_doc else None},
		{"label": "Train Status", "value": train_doc.get("status") if train_doc else None},
    ]

    primitive_summary = {
        "total_containers": total_containers,
        "loaded": loaded,
        "in_transit": in_transit,
        "received": received,
        "not_received": not_received,
        "departure_location": train_doc.get("departure_location") if train_doc else None,
        "arrival_location": train_doc.get("arrival_location") if train_doc else None,
        "loco_number": train_doc.get("loco_number") if train_doc else None,
        "break_number": train_doc.get("break_number") if train_doc else None,
        "departure_time": train_doc.get("departure_time") if train_doc else None,
        "actual_arrival_datetime": train_doc.get("actual_arrival_datetime") if train_doc else None,
		"status": train_doc.get("status") if train_doc else None
    }

    return report_summary, primitive_summary