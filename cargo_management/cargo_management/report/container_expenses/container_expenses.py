import frappe
from frappe import _

def execute(filters=None):
    expense_types = get_expense_types()
    data = get_data(filters, expense_types)
    columns = get_columns(data, expense_types)
    return columns, data

def get_expense_types():
    # Fetching all expense types from the `FPL Cost Type` DocType
    return frappe.get_all('FPL Cost Type', fields=['*'])

def get_columns(data, expense_types):
    columns = [
        {"label": _("Container Number"), "fieldname": "container_number", "fieldtype": "Data", "width": 150},
        {"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 60},
        {"label": _("Wagon"), "fieldname": "loco_number", "fieldtype": "Data", "width": 100},
        {"label": _("Category"), "fieldname": "sales_order_type", "fieldtype": "Data", "width": 100},
        {"label": _("Shipper"), "fieldname": "bill_to", "fieldtype": "Data", "width": 100},
        {"label": _("Booking #"), "fieldname": "BOName", "fieldtype": "Data", "width": 100},
        {"label": _("Movement Type"), "fieldname": "movement_type", "fieldtype": "Data", "width": 100},
        {"label": _("Rail"), "fieldname": "rail_number", "fieldtype": "Data", "width": 100},
        {"label": _("Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 150},
        {"label": _("Selling"), "fieldname": "selling_cost", "fieldtype": "Currency", "width": 150}
    ]

    # Dynamically adding expense type columns based on distinct 'collumn' values
    unique_columns = set([d.get('collumn') for d in data if d.get('collumn')])
    for uc in unique_columns:
        columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Data", "width": 120})

    return columns

def get_data(filters, expense_types):
    conditions = get_conditions(filters)
    total_cost_field = ", SUM(e.T_amount) as total_cost"
    selling_cost_calculation = """
        , CASE
            WHEN F.rate_type = 'Per Weight(Ton)' THEN F.rate * F.weight
            WHEN F.rate_type = 'Per Bag' THEN F.rate * F.bag_qty
            ELSE F.rate
        END as selling_cost
    """

    data_query = f"""
        SELECT 
            c.container_number, F.size, pm.loco_number, BO.name as BOName, BO.bill_to, BO.sales_order_type, pm.movement_type, pm.rail_number, F.rate, F.rate_type, F.weight, F.bag_qty,
            CASE 
                WHEN e.parenttype = 'FPLRoadJob' THEN CONCAT(SUBSTRING_INDEX(e.parent, '-', 1), '-', e.expense_type) 
                ELSE SUBSTRING_INDEX(e.parent, '-', 1)
            END as collumn,
            {total_cost_field}
            {selling_cost_calculation}
        FROM 
            (select container_number, expense_type, parenttype, parent, sum(amount) as T_amount from `tabExpenses cdt` Group by parent, container_number, parenttype, expense_type) as e
        JOIN `tabFPL Containers` c ON e.container_number = c.name
        JOIN `tabFPL Perform Middle Mile` pm ON pm.name = SUBSTRING_INDEX(e.parent, '-', 1)
        JOIN `tabFPL Freight Orders` F ON c.freight_order_id = F.name
        JOIN `tabBooking Order` BO on BO.name = F.sales_order_number
        WHERE
            {conditions}
        GROUP BY
            c.container_number
    """
    return frappe.db.sql(data_query, filters, as_dict=1)

def get_conditions(filters):
    conditions = []
    if filters.get("from_date"):
        conditions.append("pm.departure_time >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("pm.departure_time <= %(to_date)s")
    return " AND ".join(conditions) if conditions else "1=1"
