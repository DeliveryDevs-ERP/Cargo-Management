import frappe
from frappe import _

def execute(filters=None):
    expense_types = get_expense_types()
    data = get_data(filters, expense_types)
    columns = get_columns(data, expense_types)
    data = process_data(data)
    return columns, data

def get_expense_types():
    # Fetching all expense types from the `FPL Cost Type` DocType
    return frappe.get_all('FPL Cost Type', fields=['*'])

def get_columns(data, expense_types):
    columns = [
        {"label": _("Container Name"), "fieldname": "CName", "fieldtype": "Data", "width": 150, "hidden": True},
        {"label": _("Container Number"), "fieldname": "container_number", "fieldtype": "Data", "width": 150},
        {"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 60},
        {"label": _("Loco"), "fieldname": "loco_number", "fieldtype": "Data", "width": 100},
        {"label": _("Wagon"), "fieldname": "wagon_number", "fieldtype": "Data", "width": 100},
        {"label": _("Category"), "fieldname": "sales_order_type", "fieldtype": "Data", "width": 100},
        {"label": _("Shipper"), "fieldname": "bill_to", "fieldtype": "Data", "width": 100},
        {"label": _("Booking #"), "fieldname": "BOName", "fieldtype": "Data", "width": 100},
        {"label": _("Movement Type"), "fieldname": "movement_type", "fieldtype": "Data", "width": 100},
        {"label": _("Rail"), "fieldname": "rail_number", "fieldtype": "Data", "width": 100},
    ]

    # Dynamically adding expense type columns based on distinct 'collumn' values
    unique_columns = set([d.get('collumn') for d in data if d.get('collumn')])
    for uc in unique_columns:
        columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Currency", "width": 120})

    columns.extend([
        {"label": _("Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 150},
        {"label": _("Selling"), "fieldname": "selling_cost", "fieldtype": "Currency", "width": 150},
        {"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "width": 150},
    ])
    return columns

def get_data(filters, expense_types):
      
    selling_cost_calculation = """
    ,   CASE
            WHEN F.rate_type = 'Per Bag' THEN F.rate * F.bag_qty
            WHEN F.rate_type = 'Per Container' THEN F.rate 
            WHEN F.rate_type = 'Per Weight(Ton)' THEN F.rate * F.weight
        END as selling_cost
    """
    
    data_query = f"""
        SELECT 
           c.name as CName, AR.wagon_number, c.container_number, F.size, pm.loco_number, BO.name as BOName, BO.bill_to, BO.sales_order_type, pm.movement_type, pm.rail_number, F.rate, F.rate_type, F.weight, F.bag_qty, e.amount as total_cost,
            CASE
                WHEN e.parenttype = 'FPLRoadJob' THEN CONCAT(SUBSTRING_INDEX(e.parent, '-', 1), '-', e.expense_type)
                WHEN e.parenttype = 'FPLYardJob' THEN CONCAT(SUBSTRING_INDEX(e.parent, '-', 1), '-', e.expense_type)
                WHEN e.parenttype = 'FPL Perform Middle Mile' THEN CONCAT('Middle Mile', '-', e.expense_type)
                WHEN e.parenttype = 'Perform Cross Stuff' THEN CONCAT('Cross Stuff', '-', e.expense_type)
            END as collumn
            {selling_cost_calculation}
        FROM 
            `tabExpenses cdt` e
        JOIN
            `tabFPL Containers` c ON c.name = e.container_number
        JOIN
            `tabFPL Freight Orders` F ON c.freight_order_id = F.name
        JOIN
            `tabBooking Order` BO on BO.name = F.sales_order_number
        LEFT JOIN
            `tabFPL Perform Middle Mile` pm on pm.name = e.parent
        JOIN
            `tabNew MM cdt` AR on AR.parent = pm.name and AR.container = c.name
        WHERE
            e.container_number IN (SELECT DISTINCT c.container_number 
            FROM `tabFPL Perform Middle Mile` pm 
            JOIN `tabExpenses cdt` c ON pm.name = c.parent
            WHERE pm.departure_time BETWEEN %(from_date)s AND %(to_date)s

            UNION ALL

            SELECT DISTINCT cdt.container_number 
            FROM `tabGrounded Filled Cdt` cdt
            where cdt.reference_container in (SELECT DISTINCT c.container_number 
            FROM `tabFPL Perform Middle Mile` pm 
            JOIN `tabExpenses cdt` c ON pm.name = c.parent
            WHERE pm.departure_time BETWEEN %(from_date)s AND %(to_date)s))
    """
    return frappe.db.sql(data_query, {'from_date': filters.get("from_date"), 'to_date': filters.get("to_date")}, as_dict=True)


def process_data(data):
    processed_data = {}
    for row in data:
        container_key = row['CName']
        if container_key not in processed_data:
            processed_data[container_key] = {
                'CName': row['CName'],
                'container_number': row['container_number'],
                'wagon_number' : row['wagon_number'],
                'size': row['size'],
                'loco_number': row['loco_number'],
                'sales_order_type': row['sales_order_type'],
                'bill_to': row['bill_to'],
                'BOName': row['BOName'],
                'movement_type': row['movement_type'],
                'rail_number': row['rail_number'],
                'total_cost': 0,  # Initialize as 0 to start aggregation
                'selling_cost': row.get('selling_cost', 0)  # Safe access with default if key might not exist
            }
        else:
            if processed_data[container_key]['loco_number'] is None and row.get('loco_number') is not None:
                processed_data[container_key]['loco_number'] = row['loco_number']
            if processed_data[container_key]['movement_type'] is None and row.get('movement_type') is not None:
                processed_data[container_key]['movement_type'] = row['movement_type']
            if processed_data[container_key]['rail_number'] is None and row.get('rail_number') is not None:
                processed_data[container_key]['rail_number'] = row['rail_number']
            
        
        collumn_key = row['collumn'].replace(" ", "_").lower()
        # Add or update the expense under the correct column
        processed_data[container_key][collumn_key] = row['total_cost']
        # Accumulate total cost
        processed_data[container_key]['total_cost'] += row['total_cost']
        processed_data[container_key]['profit'] = processed_data[container_key]['selling_cost'] - processed_data[container_key]['total_cost']

    
    
    return list(processed_data.values())

