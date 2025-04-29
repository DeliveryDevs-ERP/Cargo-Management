import frappe
from frappe import _
from cargo_management.cargo_management.utils.getJobTypebyID import get_job_type_by_id

def revertJobStatus(job_id, freight_order_id, container_number):
    # Fetch the Freight Order document
    freight_order = frappe.get_doc("FPL Freight Orders", freight_order_id)
    
    if not freight_order:
        frappe.throw(f"No FPL Freight Order found with ID {freight_order_id}")
        return False

    job_found = False
    job_index = -1
    job_start_location = None
    job_end_location = None

    for idx, job in enumerate(freight_order.jobs):
        if job.job_id == job_id:
            job_found = True
            job_index = idx
            job_start_location = job.start_location
            job_end_location = job.end_location
            break

    if not job_found:
        frappe.throw(f"No job found with job_id {job_id} in the FPL Freight Order document.")
        return False

    # Second: check future jobs are NOT completed
    if job_index < len(freight_order.jobs) - 1:
        future_jobs_not_completed = all(
            freight_order.jobs[j].status != "Completed"
            for j in range(job_index + 1, len(freight_order.jobs))
        )
        if not future_jobs_not_completed:
            frappe.throw(_("Cannot revert job {0} because future jobs are already completed.").format(job_id))
            return False

    freight_order.jobs[job_index].status = "Assigned"
    freight_order.next_job = get_job_type_by_id(job_id)
    # try:
    freight_order.last_job = get_job_type_by_id(freight_order.jobs[job_index - 1].job_id) 
    # except:
    #     freight_order.last_job = None
        
    freight_order.save()

    # Fetch and update the Container document
    container = frappe.get_doc("FPL Containers", {
        "container_number": container_number,
        "freight_order_id": freight_order_id
    })
    
    if container:
        container.active_job_id = job_id
        container.state = "In transit"
        container.container_location = job_start_location
        container.container_next_location = job_end_location
        container.save()
    else:
        frappe.throw(f"No FPL Container found with container number {container_number}")
        return False

    return True
