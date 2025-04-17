import frappe
from frappe import _

def execute(filters=None):
    expense_types = get_expense_types()
    data = get_data(filters, expense_types)
    columns = get_columns(data, expense_types)
    data = process_data(data)
    if not filters.get("summaries"):
        data = calculate_bo_summary(data)
    elif filters.get("summaries"):
        columns = summarised_collumns()
        data = create_summary(data)
    return columns, data

def get_expense_types():
    # Fetching all expense types from the `FPL Cost Type` DocType
    return frappe.get_all('FPL Cost Type', fields=['*'])

def get_columns(data, expense_types):
    columns = [
        {"label": _("Container Name"), "fieldname": "CName", "fieldtype": "Data", "width": 150, "hidden": True},
        {"label": _("Container Number"), "fieldname": "container_number", "fieldtype": "Data", "width": 150},
        {"label": _("Freight Order Number"), "fieldname": "FOname", "fieldtype": "Data", "width": 150},
        {"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 60},
        {"label": _("Loco"), "fieldname": "loco_number", "fieldtype": "Data", "width": 100},
        {"label": _("Wagon"), "fieldname": "wagon_number", "fieldtype": "Data", "width": 100},
        {"label": _("Category"), "fieldname": "sales_order_type", "fieldtype": "Data", "width": 100},
        {"label": _("Shipper"), "fieldname": "bill_to", "fieldtype": "Data", "width": 100},
        {"label": _("Booking #"), "fieldname": "BOName", "fieldtype": "Data", "width": 100},
        {"label": _("Cargo Owner"), "fieldname": "cargo_owner", "fieldtype": "Data", "width": 100},
        {"label": _("Movement Type"), "fieldname": "movement_type", "fieldtype": "Data", "width": 100},
        {"label": _("Rail"), "fieldname": "rail_number", "fieldtype": "Data", "width": 100},
    ]

    # Dynamically adding expense type columns based on distinct 'collumn' values
    unique_columns = set([d.get('collumn') for d in data if d.get('collumn')])
    for uc in unique_columns:
        columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Currency", "width": 120})

    columns.extend([
        {"label": _("Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 150},
        {"label": _("Extra Invoice"), "fieldname": "extra_cost", "fieldtype": "Currency", "width": 150},
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
            ELSE 0
        END as selling_cost
    """
    
    data_query = f"""
        SELECT 
           c.name as CName, AR.wagon_number, c.container_number, F.name as FOname, F.size, F.weight as f_weight, pm.loco_number, BO.name as BOName, BO.sales_order_date as BOdate, BO.sales_person, BO.customer as BOcustomer, BO.commodity, BO.transport_type, BO.delivery_date as BODdate, BO.cargo_owner, BO.bill_to, BO.sales_order_type, pm.movement_type, pm.rail_number, F.rate, F.rate_type, F.weight, F.bag_qty, e.amount as total_cost, e.invoiced_ as invoice_tick,
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
        LEFT JOIN
            `tabNew MM cdt` AR on AR.container = c.name
        WHERE
            BO.sales_order_date BETWEEN %(from_date)s AND %(to_date)s
            AND BO.transport_type = %(transport_mode)s 
            AND e.expense_type IS NOT NULL
        ORDER BY
            BO.name
    """
    return frappe.db.sql(data_query, {'from_date': filters.get("from_date"), 'to_date': filters.get("to_date"), 'transport_mode': filters.get("transport_mode")}, as_dict=True)



def process_data(data):
    processed_data = {}
    frappe.errprint(f"This is data in Process : {data}")
    for row in data:
        container_key = row['CName']
        if container_key not in processed_data:
            processed_data[container_key] = {
                'CName': row['CName'],
                'FOname': row['FOname'],
                'sales_person': row['sales_person'],
                'container_number': row['container_number'],
                'wagon_number' : row['wagon_number'],
                'size': row['size'],
                'commodity' : row['commodity'],
                'transport_type' : row['transport_type'],
                'BOdate': row['BOdate'],
                'BOcustomer' : row['BOcustomer'],
                'BODdate' : row['BODdate'],
                'f_weight' : row['f_weight'],
                'loco_number': row['loco_number'],
                'sales_order_type': row['sales_order_type'],
                'bill_to': row['bill_to'],
                'BOName': row['BOName'],
                'movement_type': row['movement_type'],
                'rail_number': row['rail_number'],
                'total_cost': 0,  
                'extra_cost': 0,
                'cargo_owner': row['cargo_owner'],
                'selling_cost': row['selling_cost'] 
            }
        else:
            if processed_data[container_key]['loco_number'] is None and row.get('loco_number') is not None:
                processed_data[container_key]['loco_number'] = row['loco_number']
            if processed_data[container_key]['movement_type'] is None and row.get('movement_type') is not None:
                processed_data[container_key]['movement_type'] = row['movement_type']
            if processed_data[container_key]['rail_number'] is None and row.get('rail_number') is not None:
                processed_data[container_key]['rail_number'] = row['rail_number']
            
        if row['invoice_tick']:
            processed_data[container_key]['extra_cost'] += row['total_cost']
        collumn_key = row['collumn'].replace(" ", "_").lower()
        # Add or update the expense under the correct column
        processed_data[container_key][collumn_key] = row['total_cost']
        # Accumulate total cost
        processed_data[container_key]['pickup_location'] = get_pickup_location(processed_data[container_key]['BOName'],processed_data[container_key]['transport_type'])
        processed_data[container_key]['dropoff_location'] = get_dropoff_location(processed_data[container_key]['BOName'],processed_data[container_key]['transport_type'])
        processed_data[container_key]['total_cost'] += row['total_cost']
        # frappe.errprint(f"FO Name {processed_data[container_key]['FOname']}")
        if processed_data[container_key]['FOname'].split("-")[0] == 'CFO':
            processed_data[container_key]['selling_cost'] = 0
        processed_data[container_key]['profit'] = (processed_data[container_key]['selling_cost']  + processed_data[container_key]['extra_cost']) - processed_data[container_key]['total_cost'] 

    return list(processed_data.values())

def calculate_bo_summary(data):
    processed_data = {}
    for row in data:
        BO_key = row['BOName']
        if BO_key not in processed_data:
            processed_data[BO_key] = {
                'data': [],
                'total_selling_cost': 0,
                'total_cost': 0,
                'total_profit': 0
            }
        processed_data[BO_key]['data'].append(row)
        processed_data[BO_key]['total_selling_cost'] += row['selling_cost']
        processed_data[BO_key]['total_cost'] += row['total_cost']
        processed_data[BO_key]['total_profit'] += row['profit']

    summary_data = []
    for BO_key, values in processed_data.items():
        extra = fetch_extra_invoice(BO_key, values['total_selling_cost']),
        summary = {
            'BOName': f"<b>{BO_key}</b>",
            'selling_cost': values['total_selling_cost'],
            'extra_cost' : extra,
            'total_cost': values['total_cost'],
            'profit': (values['total_selling_cost'] + extra) - values['total_cost']
        }
        summary_data.extend(values['data'])
        summary_data.append(summary)

    return summary_data
    

def get_pickup_location(Booking_id, transport_mode):
    doc = frappe.get_doc("Booking Order",Booking_id)
    if transport_mode == "Rail (Train)":
        if doc.empty_pickup_location:
            return doc.empty_pickup_location
        elif doc.fm_pickup_location:
            return doc.fm_pickup_location
        elif doc.mm_loading_station:
            return doc.mm_loading_station
    elif transport_mode == "Road (Truck)":
        if doc.empty_pickup_location:
            return doc.empty_pickup_location
        elif doc.long_haul_pickup_location:
            return doc.long_haul_pickup_location
        elif doc.short_haul_pickup_location:
            return doc.short_haul_pickup_location
        
                 


def get_dropoff_location(Booking_id, transport_mode):
    doc = frappe.get_doc("Booking Order",Booking_id)
    if transport_mode == "Rail (Train)":
        if doc.empty_return_dropoff_location:
            return doc.empty_return_dropoff_location
        elif doc.lm_dropoff_location:
            return doc.lm_dropoff_location
        elif doc.mm_offloading_station:
            return doc.mm_offloading_station
    elif transport_mode == "Road (Truck)":
        if doc.empty_return_dropoff_location:
            return doc.empty_return_dropoff_location
        elif doc.long_haul_dropoff_location:
            return doc.long_haul_dropoff_location
        elif doc.short_haul_dropoff_location:
            return doc.short_haul_dropoff_location
    

   
def summarised_collumns():
    return [
        {"label": _("Booking #"), "fieldname": "BOName", "fieldtype": "Data", "width": 120},
        {"label": _("Booking Date"), "fieldname": "BOdate", "fieldtype": "Date", "width": 100},
        {"label": _("Delivery Date"), "fieldname": "BODdate", "fieldtype": "Date", "width": 100},
        {"label": _("Customer"), "fieldname": "BOcustomer", "fieldtype": "Data", "width": 120},
        {"label": _("Cargo Owner"), "fieldname": "cargo_owner", "fieldtype": "Data", "width": 120},
        {"label": _("Sales Person"), "fieldname": "sales_person", "fieldtype": "Data", "width": 120},
        {"label": _("Order Type"), "fieldname": "sales_order_type", "fieldtype": "Data", "width": 100},
        {"label": _("Commodity"), "fieldname": "commodity", "fieldtype": "Data", "width": 100},
        {"label": _("Transport Mode"), "fieldname": "transport_type", "fieldtype": "Data", "width": 110},
        {"label": _("Pickup Location"), "fieldname": "pickup_location", "fieldtype": "Data", "width": 120},
        {"label": _("Drop off Location"), "fieldname": "dropoff_location", "fieldtype": "Data", "width": 120},
        {"label": _("Selling"), "fieldname": "selling_cost", "fieldtype": "Currency", "width": 100},
        {"label": _("Extra Invoice"), "fieldname": "extra_cost", "fieldtype": "Currency", "width": 100},
        {"label": _("Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 100},
        {"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "width": 100},
    ]

def create_summary(data):
    summary_map = {}

    for row in data:
        bo = row.get('BOName')
        if not bo:
            continue

        if bo not in summary_map:
            summary_map[bo] = {
                'BOName': bo,
                'BOdate': row.get('BOdate'),
                'BODdate': row.get('BODdate'),
                'BOcustomer': row.get('BOcustomer'),
                'cargo_owner': row.get('cargo_owner'),
                'sales_person': row.get('sales_person'),
                'sales_order_type': row.get('sales_order_type'),
                'commodity': row.get('commodity'),
                'transport_type': row.get('transport_type'),
                'pickup_location': row.get('pickup_location'),
                'dropoff_location': row.get('dropoff_location'),
                'selling_cost': 0,
                'extra_cost' : 0,
                'total_cost': 0,
                'profit': 0
            }

        summary_map[bo]['selling_cost'] += row.get('selling_cost', 0) or 0
        summary_map[bo]['extra_cost'] += fetch_extra_invoice(bo, summary_map[bo]['selling_cost'])
        summary_map[bo]['total_cost'] += row.get('total_cost', 0) or 0
        summary_map[bo]['profit'] += row.get('profit', 0) or 0

    return list(summary_map.values())

def fetch_extra_invoice(booking_no, selling_amount):
    try:
        result = frappe.db.sql("""
            SELECT SUM(sii.amount) AS total_sale_amount
            FROM `tabSales Order` AS so
            LEFT JOIN `tabSales Invoice Item` AS sii ON so.name = sii.sales_order
            WHERE so.custom_booking_order_id = %s
        """, (booking_no,), as_dict=True)

        if result and result[0].get("total_sale_amount") is not None:
            return result[0]["total_sale_amount"] - selling_amount
        else:
            return 0
    except Exception as e:
        frappe.log_error(f"Error fetching invoice for booking {booking_no}: {str(e)}")
        return 0