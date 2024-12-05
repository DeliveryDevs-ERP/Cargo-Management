import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    """Define the columns for the report."""
    return [
        {"label": "Train #", "fieldname": "train_no", "fieldtype": "Data", "width": 100},
        {"label": "Loco #", "fieldname": "loco_no", "fieldtype": "Data", "width": 100},
        {"label": "Break #", "fieldname": "break_no", "fieldtype": "Data", "width": 100},
        {"label": "Movement", "fieldname": "movement", "fieldtype": "Data", "width": 100},
        {"label": "Departure Location", "fieldname": "departure_location", "fieldtype": "Data", "width": 150},
        {"label": "Arrival Location", "fieldname": "arrival_location", "fieldtype": "Data", "width": 150},
        {"label": "Departure Date", "fieldname": "departure_date", "fieldtype": "Date", "width": 120},  
        {"label": "20ft", "fieldname": "count_20", "fieldtype": "Int", "width": 120},
        {"label": "40ft", "fieldname": "count_40", "fieldtype": "Int", "width": 120},
        {"label": "Wagons: S", "fieldname": "small_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Wagons: L", "fieldname": "large_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Wagons: Conv", "fieldname": "conventional_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]

from frappe.utils import getdate

def get_data(filters):
    """Fetch and process data for the report."""
    train_no_from = int(filters.get("train_no_from").split("-")[0])
    train_no_to = int(filters.get("train_no_to").split("-")[0])
    movement = filters.get("movement")

    # Ensure train_no_from is less than train_no_to for the "between" filter
    if train_no_from > train_no_to:
        train_no_from, train_no_to = train_no_to, train_no_from
        
    # Fetch all train documents
    train_docs = frappe.get_all(
        "FPL Perform Middle Mile",
        fields=["*"],
        order_by="rail_number asc, creation asc"
    )

    if not train_docs:
        frappe.throw(_("No trains found."))

    data = []

    for train in train_docs:
        # Process only trains that qualify the range filter
        if not (train_no_from <= int(train["rail_number"]) <= train_no_to):
            continue  # Skip if train doesn't meet range

        containers = frappe.get_all(
            "FPL MM cdt",
            filters={"parent": train["name"], "parentfield": 'middle_mile_in_loading'},
            fields=["container_number"]
        )
        count_20, count_40 = 0, 0
        for container in containers:
            container_size = frappe.db.get_value(
                "FPL Freight Orders", 
                {"container_number": container["container_number"]}, 
                "size"
            )
            if container_size == 20:
                count_20 += 1
            elif container_size == 40:
                count_40 += 1

        # Process wagons as before...
        wagons = frappe.get_all(
            "FPL Wagon cdt",
            filters={"parent": train["name"]},
            fields=["wagon_type"]
        )
        wagon_types = [w["wagon_type"] for w in wagons if w["wagon_type"]]
        wagon_types = frappe.get_all(
            "FPL Wagons",
            filters={"name": ["in", wagon_types]},
            fields=["type"]
        )
        large_wagons = sum(1 for w in wagon_types if w["type"] == "Large")
        small_wagons = sum(1 for w in wagon_types if w["type"] == "Small")
        conventional_wagons = sum(1 for w in wagon_types if w["type"] == "Conventional")

        data.append({
            "train_no": train["rail_number"],
            "loco_no": train["loco_number"],
            "break_no": train["break_number"],
            "departure_location": train.get("departure_location", "N/A"),
            "arrival_location": train.get("arrival_location", "N/A"),
            "departure_date": train.get("departure_time", "N/A"),  
            "status": train.get("status", "N/A"),  
            "count_20": count_20,
            "count_40": count_40,
            "movement": train["movement_type"],
            "large_wagons": large_wagons,
            "small_wagons": small_wagons,
            "conventional_wagons": conventional_wagons,
        })

    return data
