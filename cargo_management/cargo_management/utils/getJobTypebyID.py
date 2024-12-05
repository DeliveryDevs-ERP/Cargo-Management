import frappe

def get_job_type_by_id(job_id):
    job_doctypes = ["FPLRailJob", "FPLYardJob", "FPLRoadJob"] 
    for doctype in job_doctypes:
        job_type = frappe.db.get_value(doctype, {"name": job_id}, "job_type")
        if job_type:
            service_name = frappe.db.get_value("Service Type", {"name": job_type}, "name1")
            if service_name:
                return service_name
    frappe.throw(f"No job found with job_id: {job_id} in any job doctype.")