import frappe
from frappe import _

def execute(filters=None):
    data = []
    job_types = get_job_types(filters)
    columns = get_columns(data ,job_types)
    data = get_data(filters, job_types)
    data = process_data(data, job_types)
    return columns, data

def get_job_types(filters):
    # Fetching all expense types from the `FPL Cost Type` DocType
    job_types = []
    # booking_type = filters.get("booking_type")
    transport_mode = filters.get("transport_mode")
    Jobs = frappe.get_all('FPL Jobs Sequence', filters= {"transport_mode":transport_mode, "sales_order_type": "Domestic" }, fields=['*'])
    for job in Jobs:
        service_types = frappe.get_doc('Service Type', job.service_name)
        job_types.append(service_types.name1)
    # frappe.errprint(f"job_types {job_types}")
    return job_types

 
def get_columns(data, job_types):
    """
    Transit duration : sum of all jobs durations,
    detention days: booking free date - empty return end (only if data present in collumn)
    Customer BO
    Cargo Owner BO
    Booking Date BO
    Delivery Date BO
    FO status
    FO name
    Booking Type BO
    Delivery Delay : if FO status is completed and result -ve (Delivery date - Last Job perform date) in days else 0
    """
    columns = [
        # {"label": _("Container Name"), "fieldname": "CName", "fieldtype": "Data", "width": 150, "hidden": True},
        {"label": _("Container Number"), "fieldname": "CName", "fieldtype": "Data", "width": 150},
        # {"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 60},
        # {"label": _("Loco"), "fieldname": "loco_number", "fieldtype": "Data", "width": 100},
        # {"label": _("Wagon"), "fieldname": "wagon_number", "fieldtype": "Data", "width": 100},
        # {"label": _("Category"), "fieldname": "sales_order_type", "fieldtype": "Data", "width": 100},
        # {"label": _("Shipper"), "fieldname": "bill_to", "fieldtype": "Data", "width": 100},
        {"label": _("Booking #"), "fieldname": "BOName", "fieldtype": "Data", "width": 100},
        # {"label": _("Job Name"), "fieldname": "Job_name", "fieldtype": "Data", "width": 100},

        # {"label": _("Cargo Owner"), "fieldname": "cargo_owner", "fieldtype": "Data", "width": 100},
        # {"label": _("Movement Type"), "fieldname": "movement_type", "fieldtype": "Data", "width": 100},
        # {"label": _("Rail"), "fieldname": "rail_number", "fieldtype": "Data", "width": 100},
    ]
    
    # for uc in job_types:
    #     columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Currency", "width": 120})

    for uc in job_types:
            columns.extend([
            {"label": _(uc + " Start"), "fieldname": uc.lower().replace(" ", "_") + "_start", "fieldtype": "Datetime", "width": 150},
            {"label": _(uc + " End"), "fieldname": uc.lower().replace(" ", "_") + "_end", "fieldtype": "Datetime", "width": 150},
            {"label": _(uc + " Duration"), "fieldname": uc.lower().replace(" ", "_") + "_duration", "fieldtype": "Data", "width": 100},
        ])
 
    # Dynamically adding expense type columns based on distinct 'collumn' values
    # unique_columns = set([d.get('collumn') for d in data if d.get('collumn')])
    # for uc in unique_columns:
    #     columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Currency", "width": 120})

    # columns.extend([
    #     {"label": _("Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 150},
    #     {"label": _("Selling"), "fieldname": "selling_cost", "fieldtype": "Currency", "width": 150},
    #     {"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "width": 150},
    # ])
    return columns

def get_data(filters, expense_types):
      
    # selling_cost_calculation = """
    # ,   CASE
    #         WHEN F.rate_type = 'Per Bag' THEN F.rate * F.bag_qty
    #         WHEN F.rate_type = 'Per Container' THEN F.rate 
    #         WHEN F.rate_type = 'Per Weight(Ton)' THEN F.rate * F.weight
    #         ELSE 0
    #     END as selling_cost
    # """
    
    # data_query = f"""
    #     SELECT 
    #        c.name as CName, AR.wagon_number, c.container_number, F.size, pm.loco_number, BO.name as BOName, BO.cargo_owner , BO.bill_to, BO.sales_order_type, pm.movement_type, pm.rail_number, F.rate, F.rate_type, F.weight, F.bag_qty, e.amount as total_cost,
    #         CASE
    #             WHEN e.parenttype = 'FPLRoadJob' THEN CONCAT(SUBSTRING_INDEX(e.parent, '-', 1), '-', e.expense_type)
    #             WHEN e.parenttype = 'FPLYardJob' THEN CONCAT(SUBSTRING_INDEX(e.parent, '-', 1), '-', e.expense_type)
    #             WHEN e.parenttype = 'FPL Perform Middle Mile' THEN CONCAT('Middle Mile', '-', e.expense_type)
    #             WHEN e.parenttype = 'Perform Cross Stuff' THEN CONCAT('Cross Stuff', '-', e.expense_type)
    #         END as collumn
    #         {selling_cost_calculation}
    #     FROM 
    #         `tabExpenses cdt` e
    #     JOIN
    #         `tabFPL Containers` c ON c.name = e.container_number
    #     JOIN
    #         `tabFPL Freight Orders` F ON c.freight_order_id = F.name
    #     JOIN
    #         `tabBooking Order` BO on BO.name = F.sales_order_number
    #     LEFT JOIN
    #         `tabFPL Perform Middle Mile` pm on pm.name = e.parent
    #     LEFT JOIN
    #         `tabNew MM cdt` AR on AR.parent = pm.name and AR.container = c.name
    #     WHERE
    #         e.container_number IN (SELECT DISTINCT c.container_number 
    #         FROM `tabFPL Perform Middle Mile` pm 
    #         JOIN `tabExpenses cdt` c ON pm.name = c.parent
    #         WHERE pm.departure_time BETWEEN %(from_date)s AND %(to_date)s

    #         UNION ALL

    #         SELECT DISTINCT cdt.container_number 
    #         FROM `tabGrounded Filled Cdt` cdt
    #         where cdt.reference_container in (SELECT DISTINCT c.container_number 
    #         FROM `tabFPL Perform Middle Mile` pm 
    #         JOIN `tabExpenses cdt` c ON pm.name = c.parent
    #         WHERE pm.departure_time BETWEEN %(from_date)s AND %(to_date)s))
    # """
    
    # selling_cost_calculation = """
    # ,   CASE
    #         WHEN F.rate_type = 'Per Bag' THEN F.rate * F.bag_qty
    #         WHEN F.rate_type = 'Per Container' THEN F.rate 
    #         WHEN F.rate_type = 'Per Weight(Ton)' THEN F.rate * F.weight
    #         ELSE 0
    #     END as selling_cost
    # """
    
    data_query = f"""
        SELECT 
            BO.name as BOName, FO.name , FO.container_number as CName, RD.pickup_arrival, RD.dropoff_completed, RD.job_name as Job_name, pm.departure_time as middle_mile_start, pm.actual_arrival_datetime as middle_mile_end, timediff(pm.departure_time, pm.actual_arrival_datetime) as middle_mile_duration
        FROM
            `tabBooking Order` BO
        JOIN 
            `tabFPL Freight Orders` FO on BO.name = FO.sales_order_number
        LEFT JOIN
            `tabFPLRoadJob` RD on RD.freight_order_id = FO.name and RD.sales_order_number = BO.name and RD.container_number = FO.container_number
        LEFT JOIN
            `tabFPLRailJob` RL on RL.freight_order_id = FO.name and RL.sales_order_number = BO.name and RL.container_number = FO.container_number
        LEFT JOIN
            `tabFPL Perform Middle Mile` pm on RL.train_number = pm.name
        WHERE
            BO.sales_order_date BETWEEN %(from_date)s AND %(to_date)s and
            BO.transport_type = %(transport_mode)s and
            FO.status != "Draft"
    """
    return frappe.db.sql(data_query, {'from_date': filters.get("from_date"), 'to_date': filters.get("to_date"), 'transport_mode': filters.get("transport_mode")}, as_dict=True)



# def process_data(data):
#     processed_data = {}
#     for row in data:
#         container_key = row['CName']
#         if container_key not in processed_data:
#             processed_data[container_key] = {
#                 'CName': row['CName'],
#                 'container_number': row['container_number'],
#                 'wagon_number' : row['wagon_number'],
#                 'size': row['size'],
#                 'loco_number': row['loco_number'],
#                 'sales_order_type': row['sales_order_type'],
#                 'bill_to': row['bill_to'],
#                 'BOName': row['BOName'],
#                 'movement_type': row['movement_type'],
#                 'rail_number': row['rail_number'],
#                 'total_cost': 0,  
#                 'cargo_owner': row['cargo_owner'],
#                 'selling_cost': row['selling_cost'] 
#             }
#         else:
#             if processed_data[container_key]['loco_number'] is None and row.get('loco_number') is not None:
#                 processed_data[container_key]['loco_number'] = row['loco_number']
#             if processed_data[container_key]['movement_type'] is None and row.get('movement_type') is not None:
#                 processed_data[container_key]['movement_type'] = row['movement_type']
#             if processed_data[container_key]['rail_number'] is None and row.get('rail_number') is not None:
#                 processed_data[container_key]['rail_number'] = row['rail_number']
            
        
#         collumn_key = row['collumn'].replace(" ", "_").lower()
#         # Add or update the expense under the correct column
#         processed_data[container_key][collumn_key] = row['total_cost']
#         # Accumulate total cost
#         processed_data[container_key]['total_cost'] += row['total_cost']
#         processed_data[container_key]['profit'] = processed_data[container_key]['selling_cost'] - processed_data[container_key]['total_cost']

    
    
#     return list(processed_data.values())


def process_data(data, job_types):
    processed_data = {}
    for row in data:
        container_key = row['CName']
        if container_key not in processed_data:
            processed_data[container_key] = {
                'CName': row['CName'],
                'BOName': row['BOName'],
                'middle_mile_start' : row['middle_mile_start'],
                'middle_mile_end' : row['middle_mile_end']
            }            
            if row['middle_mile_start'] and row['middle_mile_end']:
                duration2 = row['middle_mile_end'] - row['middle_mile_start']
                processed_data[container_key]["middle_mile_duration"] = duration2.total_seconds() / 3600
            else:
                processed_data[container_key]["middle_mile_duration"] = 0
            
            for job in job_types:
                if row['Job_name'] == job:
                    index = row['Job_name'].lower().replace(" ", "_")
                    
                    processed_data[container_key][f"{index}_start"] = row['pickup_arrival']
                    processed_data[container_key][f"{index}_end"] = row['dropoff_completed']

                    if row['dropoff_completed'] and row['pickup_arrival']:
                        duration = row['dropoff_completed'] - row['pickup_arrival']
                        processed_data[container_key][f"{index}_duration"] = duration.total_seconds() / 3600
                    else:
                        processed_data[container_key][f"{index}_duration"] = 0
        
        else:   
            for job in job_types:
                if row['Job_name'] == job:
                    index = row['Job_name'].lower().replace(" ", "_")
                    
                    processed_data[container_key][f"{index}_start"] = row['pickup_arrival']
                    processed_data[container_key][f"{index}_end"] = row['dropoff_completed']

                    if row['dropoff_completed'] and row['pickup_arrival']:
                        duration = row['dropoff_completed'] - row['pickup_arrival']
                        processed_data[container_key][f"{index}_duration"] = duration.total_seconds() / 3600
                    else:
                        processed_data[container_key][f"{index}_duration"] = 0
                            
    
    return list(processed_data.values())
