import frappe
from cargo_management.cargo_management.utils.getJobTypebyID import get_job_type_by_id
# import sys

# sys.setrecursionlimit(10**6)
def updateJobStatus(job_id, freight_order_id, container_number):
    # Fetch the Freight Order document
    freight_order = frappe.get_doc("FPL Freight Orders", freight_order_id)
    
    if not freight_order:
        frappe.throw(f"No FPL Freight Order found with ID {freight_order_id}")
        return False

    job_found = False
    next_job_id = None
    next_job_start_location = None
    last_job_end_location = None
    next_next_job_location = None
    
    for i, job in enumerate(freight_order.jobs):
        if job.job_id == job_id:
            # If the job is not the first one, validate that all previous jobs are completed
            if i > 0:
                previous_jobs_completed = all(freight_order.jobs[j].status == "Completed" for j in range(i))
                if not previous_jobs_completed:
                    # frappe.msgprint(f"Cannot complete job {job_id} as previous jobs are not marked as completed.")
                    return False
            
            # Mark the job as completed if all previous jobs are completed
            job.status = "Completed"
            job_found = True
            freight_order.last_job = get_job_type_by_id(job_id)
            last_job_end_location = job.end_location 
            
            # Check if there is a next job
            if i + 1 < len(freight_order.jobs):
                next_job = freight_order.jobs[i + 1]
                next_job_id = next_job.job_id
                next_job_start_location = next_job.start_location
                freight_order.next_job = get_job_type_by_id(next_job_id)
                
                # Check if there is a job after the next job for container_next_location
                if i + 2 < len(freight_order.jobs):
                    if get_job_type_by_id(freight_order.jobs[i + 2].job_id) == "Gate Out":
                        next_next_job_location = freight_order.jobs[i + 2].end_location
                    else:
                        next_next_job_location = freight_order.jobs[i + 2].start_location
                else:
                    next_next_job_location = None
                
                if freight_order.status is None or freight_order.status == 'Draft':
                    freight_order.status = 'In Progress'
            else:
                freight_order.next_job = None
                next_next_job_location = None
            break

    if not job_found:
        frappe.throw(f"No job found with job_id {job_id} in the FPL Freight Order document.")
        return False
    # Save the updated Freight Order document
    freight_order.save()
    
    # Fetch and update the Container document
    container = frappe.get_doc("FPL Containers", {"container_number": container_number, "freight_order_id": freight_order_id})
    
    if container:
        container.status = "Filled" if next_job_id else "Empty"
        container.state = "In transit" if next_job_id else "Delivered"
        container.active_job_id = next_job_id if next_job_id else None
        container.container_location = next_job_start_location if next_job_start_location else last_job_end_location
        container.container_next_location = next_next_job_location
        container.save()
    else:
        frappe.throw(f"No FPL Container found with container number {container_number}")
        return False
    
    return True