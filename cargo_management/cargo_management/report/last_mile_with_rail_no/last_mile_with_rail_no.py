import frappe

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "name", "label": "Job Name", "fieldtype": "Link", "options": "FPLRoadJob", "width": 200},
        {"fieldname": "container_number", "label": "Container Number", "fieldtype": "Data", "width": 150},
        {"fieldname": "train_number", "label": "Train Number", "fieldtype": "Link", "options": "FPLRailJob", "width": 150},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100}
    ]

def get_data(filters):
    data = frappe.db.sql('''
        SELECT DISTINCT
            road.name, road.container_number, rail.train_number, road.status
        FROM
            `tabFPLRoadJob` AS road
        JOIN
            `tabFPLRailJob` AS rail ON road.container_number = rail.container_number
        WHERE
            road.status = 'Assigned'
            AND road.job_name = 'Last Mile'
            AND rail.train_number IS NOT NULL
    ''', as_dict=True)
    return data
