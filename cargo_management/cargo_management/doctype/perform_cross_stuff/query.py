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
