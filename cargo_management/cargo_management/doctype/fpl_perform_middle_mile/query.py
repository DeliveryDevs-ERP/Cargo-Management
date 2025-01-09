import frappe


@frappe.whitelist()
def get_applicable_jobs(*args, **kwargs):
    txt = kwargs.get('txt', '')
    searchfield = kwargs.get('searchfield', None)
    start = int(kwargs.get('start', 0))
    page_len = int(kwargs.get('page_len', 20))
    filters = kwargs.get('filters', {})
    departure_location = args[5].get('container_location')
    arrival_location = args[5].get('container_next_location')
   
    try:
        return frappe.db.sql("""
            SELECT 
                container.name, container.container_number
            FROM 
                `tabFPL Containers` AS container
            JOIN 
                `tabFPL Freight Orders` AS freight_order ON container.freight_order_id = freight_order.name
            JOIN
                `tabFPL Jobs` AS Jobs ON Jobs.parent = freight_order.name
            WHERE
                freight_order.last_job = 'Gate In' AND
                freight_order.next_job = 'Gate Out' AND
                Jobs.job_name = "oagb0ddmuo" AND
                freight_order.mm_completed_ = 0 AND
                Jobs.start_location = %s AND
                Jobs.end_location = %s
            """, (departure_location,arrival_location),
            )
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to execute SQL query in get_applicable_jobs")
        frappe.throw(("Error fetching container data: {0}").format(str(e)))




@frappe.whitelist()
def get_containers_from_Loading(*args, **kwargs):
    txt = kwargs.get('txt', '')
    searchfield = kwargs.get('searchfield', None)
    start = int(kwargs.get('start', 0))
    page_len = int(kwargs.get('page_len', 20))
    filters = kwargs.get('filters', {})
    parent = args[5].get('parent')
   
    try:
        return frappe.db.sql("""
            SELECT DISTINCT
                Loading.container, Loading.container_number
            FROM 
                `tabFPL MM cdt` AS Loading
            WHERE
                Loading.container IS NOT NULL AND
                Loading.parentfield = 'middle_mile' AND
                Loading.parent = %s
            """, (parent,))
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to execute SQL query in get_containers_from_Loading")
        frappe.throw(("Error fetching container data: {0}").format(str(e)))