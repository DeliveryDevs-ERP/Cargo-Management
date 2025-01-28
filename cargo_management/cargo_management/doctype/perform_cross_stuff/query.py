import frappe

@frappe.whitelist()
def get_unique_service_types(*args, **kwargs):
    return frappe.db.sql("""
        SELECT MIN(name) AS name, name1 
        FROM `tabService Type`
        GROUP BY name1
        ORDER BY name1
    """)
    
   

@frappe.whitelist()
def get_FO_containers(doctype, txt, searchfield, start, page_len, filters):
    """
    Fetch containers associated with FPL Freight Orders for the given booking_order_id
    where container status is 'Filled' and name starts with 'FPL-FP%'.
    """
    booking_order_id = filters.get('booking_order_id')
    
    if not booking_order_id:
        frappe.throw("Booking Order ID is required to fetch containers.")
    
    return frappe.db.sql("""
        SELECT 
            container.name, container.container_number
        FROM 
            `tabFPL Containers` AS container
        JOIN 
            `tabFPL Freight Orders` AS freight_order 
            ON container.freight_order_id = freight_order.name
        WHERE 
            freight_order.sales_order_number = %(booking_order_id)s
            AND container.status = 'Filled'
            AND freight_order.name LIKE 'FO-%%'
    """, {
        'booking_order_id': booking_order_id
    })


@frappe.whitelist()
def get_CFO_containers(doctype, txt, searchfield, start, page_len, filters):
    """
    Fetch containers associated with FPL Freight Orders for the given booking_order_id
    where container status is 'Filled' and name starts with 'FPL-CFO%'.
    """
    booking_order_id = filters.get('booking_order_id')
    
    if not booking_order_id:
        frappe.throw("Booking Order ID is required to fetch containers.")
    
    return frappe.db.sql("""
        SELECT 
            container.name, container.container_number
        FROM 
            `tabFPL Containers` AS container
        JOIN 
            `tabFPL Freight Orders` AS freight_order 
            ON container.freight_order_id = freight_order.name
        WHERE 
            freight_order.sales_order_number = %(booking_order_id)s
            AND container.status = 'Filled'
            AND freight_order.name LIKE 'CFO-%%'
    """, {
        'booking_order_id': booking_order_id
    })


@frappe.whitelist()
def get_BOs_name(doctype, txt, searchfield, start, page_len, filters):
    # SQL query to fetch booking_order_ids from documents that meet the conditions
    return frappe.db.sql("""
        SELECT booking_order_id
        FROM `tabContainer or Vehicle Request`
        WHERE docstatus = 1 AND cross_stuff_performance IS NULL
        """)
    


@frappe.whitelist()
def get_Containers_for_CS_expenses(*args, **kwargs):
    txt = kwargs.get('txt', '')
    searchfield = kwargs.get('searchfield', None)
    start = int(kwargs.get('start', 0))
    page_len = int(kwargs.get('page_len', 20))
    filters = kwargs.get('filters', {})
    in_container = args[5].get('in_container')
    frappe.errprint(f'not_in_container_list Array : {in_container}')
    in_container_list = tuple(in_container)
    frappe.errprint(f'not_in_container_list Tuple: {in_container_list}')

    try:
        sql_query = """
            SELECT 
                container.name, container.container_number
            FROM 
                `tabFPL Containers` AS container
            """
        # Add IN clause if there are containers to include
        if in_container_list:
            sql_query += " where container.name IN %s"
            return frappe.db.sql(sql_query, (in_container_list,))
        else:
            return frappe.db.sql(sql_query)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to execute SQL query in get_applicable_jobs")
        frappe.throw(f"Error fetching container data: {str(e)}")
