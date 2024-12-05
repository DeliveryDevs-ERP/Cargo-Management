import frappe

@frappe.whitelist()
def get_applicable_containers(*args, **kwargs):
    filters = kwargs.get('filters', {})
    job_type = filters.get('job_type')

    try:
        # Construct the base SQL query
        query = frappe.db.sql(f"""
            SELECT 
                container.name, 
                container.container_number 
            FROM 
                `tabFPL Containers` AS container
            JOIN 
                `tabFPLRoadJob` AS road_job 
            ON 
                container.freight_order_id = road_job.freight_order_id
            WHERE 
                container.container_location = road_job.job_start_location
        """)
        return query

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to execute SQL query in get_applicable_containers")
        frappe.throw(("Error fetching container data: {0}").format(str(e)))
