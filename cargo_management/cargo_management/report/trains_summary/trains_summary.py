import frappe
from frappe import _
from frappe.utils import date_diff, format_duration, now_datetime

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
        {"label": "Loading Start", "fieldname": "loading_start", "fieldtype": "Date", "width": 120},  
        {"label": "Loading End", "fieldname": "loading_end", "fieldtype": "Date", "width": 120},   
        {"label": "Loading Duration", "fieldname": "loading_duration", "fieldtype": "Data", "width": 120},
        {"label": "Departure Date", "fieldname": "departure_date", "fieldtype": "Date", "width": 120},  
        {"label": "Arrival Date", "fieldname": "arrival_date", "fieldtype": "Date", "width": 120}, 
        {"label": "Transit Time", "fieldname": "transit_time", "fieldtype": "Data", "width": 120},
        {"label": "20ft", "fieldname": "count_20", "fieldtype": "Int", "width": 120},
        {"label": "40ft", "fieldname": "count_40", "fieldtype": "Int", "width": 120},
        {"label": "Total Containers", "fieldname": "t_cont", "fieldtype": "Int", "width": 120},
        {"label": "Empty Wagons", "fieldname": "empty_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Loaded Wagons", "fieldname": "loaded_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Wagons: S", "fieldname": "small_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Wagons: L", "fieldname": "large_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Wagons: Conv", "fieldname": "conventional_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Total Wagons", "fieldname": "t_wagons", "fieldtype": "Int", "width": 120},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]

from frappe.utils import getdate

def get_data(filters):
    """Fetch and process data for the report."""
    
    if filters.get("train_no_from") is None or filters.get("train_no_to") is None:
        return []

    train_no_from = getdate(filters.get("train_no_from"))
    train_no_to = getdate(filters.get("train_no_to"))
    movement = filters.get("movement")
    conditions = {
        "departure_time": ["between", [train_no_from, train_no_to]]
    }
    # Ensure train_no_from is less than train_no_to for the "between" filter
    if train_no_from > train_no_to:
        train_no_from, train_no_to = train_no_to, train_no_from
        
    if movement:
        conditions['movement_type'] = movement    
    # Fetch all train documents
    train_docs = frappe.get_all(
        "FPL Perform Middle Mile",
        fields=["*"],
        filters=conditions,
        order_by="rail_number asc, creation asc"
    )

    if not train_docs:
        return []
    
    data = []
    for train in train_docs:
        # Process only trains that qualify the range filter
        if not (frappe.utils.get_datetime(train_no_from) <= train["departure_time"] <= frappe.utils.get_datetime(train_no_to)):
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
            fields=["wagon_type","loaded_"]
        )
        wagon_types = [w["wagon_type"] for w in wagons if w["wagon_type"]]
        wagon_T = []
        for type1 in wagon_types:
            wagon_types = frappe.get_all(
                "FPL Wagons",
                filters={"name": ["in", type1]},
                fields=["type"]
            )
            wagon_T.extend(wagon_types)
        wagon_types = wagon_T
        loaded_wagons = sum(1 for w in wagons if w["loaded_"] == 1)
        empty_wagons = sum(1 for w in wagons if w["loaded_"] == 0)
        large_wagons = sum(1 for w in wagon_types if w["type"] == "Large")
        small_wagons = sum(1 for w in wagon_types if w["type"] == "Small")
        conventional_wagons = sum(1 for w in wagon_types if w["type"] == "Conventional")
        
        if train.get("loading_time") and train.get("loading_end_time"):
            loading_duration_seconds = date_diff(train["loading_end_time"], train["loading_time"]) * 24 * 3600
            loading_duration = format_duration(loading_duration_seconds)
        else:
            loading_duration = ""
            
        if train.get("departure_time") and train.get("actual_arrival_datetime"):
            transit_time_seconds = date_diff(train["actual_arrival_datetime"], train["departure_time"]) * 24 * 3600
            transit_time = format_duration(transit_time_seconds)
        else:
            transit_time = ""

        data.append({
            "train_no": train["rail_number"],
            "loco_no": train["loco_number"],
            "break_no": train["break_number"],
            "departure_location": train.get("departure_location", "N/A"),
            "arrival_location": train.get("arrival_location", "N/A"),
            "departure_date": train.get("departure_time", "N/A"),  
            "loading_start": train.get("loading_time", "N/A"),  
            "loading_end": train.get("loading_end_time", "N/A"),  
            "empty_wagons": empty_wagons,
            "loaded_wagons": loaded_wagons,
            "loading_duration": loading_duration,
            "arrival_date": train.get("actual_arrival_datetime", "N/A"),  
            "transit_time": transit_time,
            "status": train.get("status", "N/A"),  
            "count_20": count_20,
            "count_40": count_40,
            "t_cont" : count_20 + count_40,
            "movement": train["movement_type"],
            "large_wagons": large_wagons,
            "small_wagons": small_wagons,
            "conventional_wagons": conventional_wagons,
            "t_wagons" :large_wagons + small_wagons + conventional_wagons,
        })
        
    return data
