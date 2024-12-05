import frappe
from datetime import timedelta

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    """Define the columns for the report."""
    return [
        {"label": "S.No", "fieldname": "s_no", "fieldtype": "Int", "width": 50},
        {"label": "Containers No", "fieldname": "container_no", "fieldtype": "Data", "width": 120},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data", "width": 80},
        {"label": "WT/MT", "fieldname": "weight", "fieldtype": "Data", "width": 100},
        {"label": "Seal Nos", "fieldname": "seal_no", "fieldtype": "Data", "width": 120},
        {"label": "Shipping Line", "fieldname": "shipping_line", "fieldtype": "Data", "width": 150},
        {"label": "Consignee", "fieldname": "consignee", "fieldtype": "Data", "width": 150},
        {"label": "BL#", "fieldname": "bill_of_landing_number", "fieldtype": "Data", "width": 150},
        {"label": "POD", "fieldname": "pod", "fieldtype": "Data", "width": 150},
        {"label": "Sales Person", "fieldname": "sales_person", "fieldtype": "Data", "width": 150},
        {"label": "Cntr Grounded (Date/Time)", "fieldname": "gate_in_datetime", "fieldtype": "Datetime", "width": 200},
    ]

def get_data(filters):
    """Fetch data for the report."""
    container_size = filters.get("container_size") if filters else None
    gate_in_location = filters.get("gate_in_location") if filters else None
    filter_date = filters.get("gate_in_date") if filters else None

    # Ensure filter_date is parsed correctly
    if filter_date:
        try:
            filter_date = frappe.utils.get_datetime(filter_date)
        except Exception as e:
            frappe.throw(f"Invalid filter date format: {e}")

    data = []
    s_no = 1

    # Step 1: Fetch FPLYardJobs for Gate In
    gate_in_jobs = frappe.get_all(
        "FPLYardJob",
        filters={
            "job_type": "enrhva2nvi",
            "job_start_location": gate_in_location,
            "status": "Completed"
        },
        fields=["container_number", "gate_in"]
    )

    # Step 2: Fetch FPLYardJobs for Gate Out
    gate_out_jobs = frappe.get_all(
        "FPLYardJob",
        filters={
            "job_type": "eo0ldr6jda",  # Gate Out type
            "job_start_location": gate_in_location,
            "status": "Completed"
        },
        fields=["container_number", "gate_out"]
    )

    # Step 3: Create a "super array" with container_number as the key
    super_array = {}
    for job in gate_in_jobs:
        container = job["container_number"]
        super_array[container] = {"gate_in": job["gate_in"], "gate_out": None}

    for job in gate_out_jobs:
        container = job["container_number"]
        if container in super_array:
            super_array[container]["gate_out"] = job["gate_out"]

    # Step 4: Filter containers based on the filter_date
    valid_containers = {
        container: times
        for container, times in super_array.items()
        if times["gate_in"] and times["gate_out"] and times["gate_in"] <= filter_date + timedelta(days=1) <= times["gate_out"]
    }

    # Step 5: Fetch data for valid containers
    for container_number, times in valid_containers.items():
        # Fetch Freight Orders for the container
        freight_orders = frappe.get_all(
            "FPL Freight Orders",
            filters={"container_number": container_number, "size": container_size} if container_size else {"container_number": container_number},
            fields=["name", "container_number", "size", "weight", "seal_no", "sales_order_number"]
        )

        for fo in freight_orders:
            # Fetch the first job from the child table "jobs" in FPL Freight Orders
            job_data = frappe.get_all(
                "FPL Jobs",
                filters={"parent": fo["name"]},  # Link with parent Freight Order
                fields=["start_location"],
                order_by="idx asc",  # Ensure the first job is fetched
                limit=1
            )

            # Extract the POD (start_location) if available
            pod = job_data[0]["start_location"] if job_data else None

            # Fetch the linked Booking Order
            booking_order = frappe.get_value(
                "Booking Order",
                {"name": fo["sales_order_number"]},
                ["shipping_line", "bill_to", "bill_of_landing_number", "sales_person"],
                as_dict=True
            )

            # Add data row
            data.append({
                "s_no": s_no,
                "container_no": fo["container_number"],
                "size": fo["size"],
                "weight": fo["weight"],
                "seal_no": fo["seal_no"],
                "shipping_line": booking_order["shipping_line"] if booking_order else None,
                "consignee": booking_order["bill_to"] if booking_order else None,
                "bill_of_landing_number": booking_order["bill_of_landing_number"] if booking_order else None,
                "pod": pod,
                "sales_person": booking_order["sales_person"] if booking_order else None,
                "gate_in_datetime": times["gate_in"],
                "gate_out_datetime": times["gate_out"],
            })
            s_no += 1

    return data


