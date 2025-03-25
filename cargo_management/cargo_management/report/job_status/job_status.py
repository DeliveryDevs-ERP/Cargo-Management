import frappe
from frappe import _

def execute(filters=None):
    data = columns = []
    job_types = get_job_types(filters)

    columns = get_columns(data ,job_types)
    if filters.get("transport_mode") == "Rail (Train)" and filters.get("check_train"):
        data = get_data_rail_trains(filters, job_types)
    if filters.get("transport_mode") == "Rail (Train)" and filters.get("check_booking"):
        data = get_data_rail_bookings(filters, job_types)
    if filters.get("transport_mode") == "Road (Truck)":
        data = get_data_road(filters, job_types)
        
    data = process_data(data, job_types)
    return columns, data

def get_job_types(filters):
    job_types = []
    transport_mode = filters.get("transport_mode")
    Jobs = frappe.get_all('FPL Jobs Sequence', filters= {"transport_mode":transport_mode, "sales_order_type": "Domestic" }, fields=['*'])
    for job in Jobs:
        service_types = frappe.get_doc('Service Type', job.service_name)
        job_types.append(service_types.name1)
    return job_types

 
def get_columns(data, job_types):
    columns = [
        # {"label": _("Container Name"), "fieldname": "CName", "fieldtype": "Data", "width": 150, "hidden": True},
        {"label": _("Container Number"), "fieldname": "CName", "fieldtype": "Data", "width": 150},
        {"label": _("Freight Status"), "fieldname": "FO_status", "fieldtype": "Data", "width": 150},
        # {"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 60},
        # {"label": _("Loco"), "fieldname": "loco_number", "fieldtype": "Data", "width": 100},
        # {"label": _("Wagon"), "fieldname": "wagon_number", "fieldtype": "Data", "width": 100},
        # {"label": _("Category"), "fieldname": "sales_order_type", "fieldtype": "Data", "width": 100},
        # {"label": _("Shipper"), "fieldname": "bill_to", "fieldtype": "Data", "width": 100},
        {"label": _("Booking #"), "fieldname": "BOName", "fieldtype": "Data", "width": 100},
        {"label": _("Booking Status"), "fieldname": "BO_status", "fieldtype": "Data", "width": 150},
        # {"label": _("Job Name"), "fieldname": "Job_name", "fieldtype": "Data", "width": 100},

        # {"label": _("Cargo Owner"), "fieldname": "cargo_owner", "fieldtype": "Data", "width": 100},
        # {"label": _("Movement Type"), "fieldname": "movement_type", "fieldtype": "Data", "width": 100},
        # {"label": _("Rail"), "fieldname": "rail_number", "fieldtype": "Data", "width": 100},
    ]
    
    # for uc in job_types:
    #     columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Currency", "width": 120})

    for uc in job_types:
            columns.extend([
            {"label": _(uc), "fieldname": uc.lower().replace(" ", "_") + "_status", "fieldtype": "Data", "width": 150},
        ])
 
    # Dynamically adding expense type columns based on distinct 'collumn' values
    # unique_columns = set([d.get('collumn') for d in data if d.get('collumn')])
    # for uc in unique_columns:
    #     columns.append({"label": _(uc), "fieldname": uc.replace(" ", "_").lower(), "fieldtype": "Currency", "width": 120})

    columns.extend([
        {"label": _("Request"), "fieldname": "req_status", "fieldtype": "Data", "width": 150},
        {"label": _("Perform Cross Stuff"), "fieldname": "crossstuff_status", "fieldtype": "Data", "width": 150},
    ])
    return columns

def get_data_rail_trains(filters, expense_types):      
    data_query = f"""
        SELECT 
            BO.name as BOName, BO.workflow_state as BO_status, FO.status as FO_status, FO.name as Fname, FO.container_number as CName, RD.status as RD_status, RD.job_name as Job_name, pm.status as middle_mile_status
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
			pm.name in %(train_nos)s and
            BO.transport_type = %(transport_mode)s and
            FO.status != "Draft"
    """
    return frappe.db.sql(data_query, {'transport_mode': filters.get("transport_mode"), 'train_nos': filters.get("train_nos")}, as_dict=True)

def get_data_rail_bookings(filters, expense_types):      
    data_query = f"""
        SELECT 
            BO.name as BOName, BO.workflow_state as BO_status, FO.status as FO_status, FO.name as Fname, FO.container_number as CName, RD.status as RD_status, RD.job_name as Job_name, pm.status as middle_mile_status
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


def get_data_road(filters, expense_types):      
    data_query = f"""
        SELECT 
            BO.name as BOName, BO.workflow_state as BO_status, FO.status as FO_status, FO.name as Fname, FO.container_number as CName, RD.status as RD_status, RD.job_name as Job_name, pm.status as middle_mile_status
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



def process_data(data, job_types):
    processed_data = {}
    for row in data:
        container_key = row['CName']
        if container_key not in processed_data:
            processed_data[container_key] = {
                'CName': row['CName'],
                'FO_status': row['FO_status'],
                'BO_status': row['BO_status'],
                'BOName': row['BOName'],
                'middle_mile_status' : row['middle_mile_status'],
            }
            
            
            Req = frappe.get_list("Container or Vehicle Request", {"booking_order_id": processed_data[container_key]['BOName']})
            if len(Req) > 0:
                processed_data[container_key]["req_status"] = "Yes"
            # else:
            #     processed_data[container_key]["req_status"] = "No"
                
                
            container = frappe.get_value("FPL Containers", {'container_number': processed_data[container_key]['CName'], 'freight_order_id': row['Fname']}, "name")
            PC = frappe.db.sql("""SELECT reference_container, container_number FROM `tabGrounded Filled Cdt`""", as_dict=1)    
            for record in PC:
                if container == record['reference_container'] or container == record['container_number']:
                    processed_data[container_key]['crossstuff_status'] = "Completed"
                    break 
            
            for job in job_types:
                if row['Job_name'] == job:
                    index = row['Job_name'].lower().replace(" ", "_")
                    processed_data[container_key][f"{index}_status"] = row['RD_status']
        else:   
            for job in job_types:
                if row['Job_name'] == job:
                    index = row['Job_name'].lower().replace(" ", "_")
                    processed_data[container_key][f"{index}_status"] = row['RD_status']

    return list(processed_data.values())
