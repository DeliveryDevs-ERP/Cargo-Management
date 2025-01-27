import frappe

@frappe.whitelist()
def get_applicable_containers(*args, **kwargs):
    filters = kwargs.get('filters', {})
    job_start_location = args[5].get('job_start_location')
    not_in_container_number = args[5].get('not_in_container_number')
    not_in_container_numbers = tuple(not_in_container_number.split(",")) if not_in_container_number else ()
    try:
        # Construct the base SQL query
        return frappe.db.sql("""
            SELECT 
                container.name, 
                container.container_number
            FROM 
                `tabFPL Containers` AS container
            JOIN 
                `tabFPLRoadJob` AS road_job 
            ON 
                container.freight_order_id = road_job.freight_order_id
            JOIN 
                `tabContainer Type` AS Type
            ON
                container.container_type = Type.name
            WHERE 
                container.container_location = road_job.job_start_location AND
                road_job.job_start_location = %s AND
                Type.size = 20 AND
                road_job.status = 'Assigned' AND
                container.container_number NOT IN %s
        """, (job_start_location,not_in_container_numbers,))
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to execute SQL query in get_applicable_containers")
        frappe.throw(("Error fetching container data: {0}").format(str(e)))
