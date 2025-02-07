import frappe


@frappe.whitelist()
def get_applicable_jobs(*args, **kwargs):
    # Extract parameters from filters
    txt = kwargs.get('txt', '')
    searchfield = kwargs.get('searchfield', None)
    start = int(kwargs.get('start', 0))
    page_len = int(kwargs.get('page_len', 20))
    filters = kwargs.get('filters', {})
    departure_location = args[5].get('container_location')
    arrival_location = args[5].get('container_next_location')
    not_in_container = args[5].get('not_in_container')
    # not_in_container_list = tuple(not_in_container.split(',')) if not_in_container else ()
    frappe.errprint(f'not_in_container_list Array : {not_in_container}')

    # Convert not_in_container string to a list, then to a tuple
    # not_in_container_list = tuple(not_in_container.split(',')) if not_in_container else tuple()
    not_in_container_list = tuple(not_in_container)
    frappe.errprint(f'not_in_container_list Tuple: {not_in_container_list}')

    try:
        sql_query = """
            SELECT 
                container.name, container.container_number, freight_order.size
            FROM 
                `tabFPL Containers` AS container
            JOIN 
                `tabFPL Freight Orders` AS freight_order ON container.freight_order_id = freight_order.name
            JOIN
                `tabFPL Jobs` AS Jobs ON Jobs.parent = freight_order.name
            WHERE
                freight_order.last_job = 'Gate In' AND
                freight_order.next_job = 'Gate Out' AND
                Jobs.job_name = 'oagb0ddmuo' AND
                freight_order.mm_completed_ = 0 AND
                Jobs.start_location = %s AND
                Jobs.end_location = %s
        """
        # Add NOT IN clause if there are items to exclude
        if not_in_container_list:
            sql_query += " AND container.name NOT IN %s"
            sql_query += " ORDER BY container.container_number, freight_order.size ASC"
            return frappe.db.sql(sql_query, (departure_location, arrival_location, not_in_container_list))
        else:
            return frappe.db.sql(sql_query, (departure_location, arrival_location))
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to execute SQL query in get_applicable_jobs")
        frappe.throw(f"Error fetching container data: {str(e)}")



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
        
        
import frappe

@frappe.whitelist()
def fetch_wagons_from_undeparted_trains(departure_location, movement_type):
    query = """
        SELECT 
            D.wagon_number,
            D.container,
            D.container_number,
            D.weight,
            D.size,
            D.parent,
            W.wagon_type
        FROM 
            `tabFPL MM cdt` D
        LEFT JOIN 
            `tabFPL Wagon cdt` W ON D.wagon_number = W.wagon_number AND W.parent = D.parent
        LEFT JOIN 
            `tabFPL Perform Middle Mile` PM ON PM.name = D.parent
        WHERE 
            D.parentfield = 'middle_mile_in_loading'
            AND D.loaded_ = 1
            AND D.departed_ = 0
            AND PM.departure_location = %s
            AND PM.movement_type = %s
            AND D.wagon_number NOT IN (
                SELECT DISTINCT wagon_number 
                FROM `tabFPL MM cdt`
                WHERE departed_ = 1
            )
    """
    wagons = frappe.db.sql(query, (departure_location, movement_type), as_dict=True)
    return wagons
