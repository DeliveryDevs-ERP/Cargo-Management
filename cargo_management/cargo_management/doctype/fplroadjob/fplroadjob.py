from cargo_management.cargo_management.utils.Update_JOB_Container_FO_Status import updateJobStatus
from frappe.utils import now_datetime
from frappe.model.document import Document
import frappe

class FPLRoadJob(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from cargo_management.cargo_management.doctype.expenses_cdt.expenses_cdt import Expensescdt
        from frappe.types import DF

        assigned_at: DF.Datetime | None
        client: DF.Link | None
        container_number: DF.Data | None
        container_number_to_link: DF.Link | None
        double_20_: DF.Check
        driver_name: DF.Data | None
        dropoff_arrival: DF.Datetime | None
        dropoff_completed: DF.Datetime | None
        expenses: DF.Table[Expensescdt]
        freight_order_id: DF.Data | None
        job_end_location: DF.Link | None
        job_start_location: DF.Link | None
        job_type: DF.Link | None
        pickup_arrival: DF.Datetime | None
        pickup_departure: DF.Datetime | None
        sales_order_number: DF.Data | None
        status: DF.Literal["Draft", "Assigned", "Completed", "Cancelled"]
        vehicle_number: DF.Data | None
        vehicle_supplier: DF.Link | None
    # end: auto-generated types

    def validate(self):
        frappe.errprint(f"Status of Job :{self.name} - {self.status}")
        if (self.vehicle_number and self.vehicle_supplier) and (self.pickup_arrival and self.pickup_departure) and (self.dropoff_arrival and self.dropoff_completed) and self.status != "Completed":
            self.status = "Completed"
            updateJobStatus(self.name, self.freight_order_id, self.container_number)
            self.completeNextGateIn()

        if self.container_number_to_link:
            self.sync_with_linked_job()

        if self.status == "Assigned":
            self.assigned_at = now_datetime()   
            
    def completeNextGateIn(self):
        freight_order = frappe.get_doc("FPL Freight Orders", self.freight_order_id)
        jobs = freight_order.jobs  # Assuming 'jobs' is the child table of Freight Order containing job references
        # Find current job index
        current_job_index = next((index for (index, job) in enumerate(jobs) if job.job_id == self.name), None)
        # Check if next job is 'Gate In' type
        if current_job_index is not None and current_job_index + 1 < len(jobs):
            next_job = jobs[current_job_index + 1]
            if next_job.job_name == "enrhva2nvi":  # Assuming there is a 'job_name' field in the job entries enrhva2nvi == Gate In
                yard_job = frappe.get_doc("FPLYardJob", next_job.job_id)
                yard_job.gate_in = self.dropoff_completed
                yard_job.save(ignore_permissions=True)

                

    def sync_with_linked_job(self):
        # Prevent recursion by setting a temporary flag
        if hasattr(self, "_is_syncing") and self._is_syncing:
            return
        self._is_syncing = True

        # Retrieve the container number based on container_number_to_link
        container_number = frappe.db.get_value("FPL Containers", {"name": self.container_number_to_link}, "container_number")

        # Get the name of the linked FPLRoadJob based on the container number and job type
        linked_job_name = frappe.db.get_value("FPLRoadJob", {"container_number": container_number, "job_type": self.job_type}, "name")

        if linked_job_name:
            linked_job = frappe.get_doc("FPLRoadJob", linked_job_name)

            # List of fields to sync
            fields_to_sync = ["pickup_arrival", "pickup_departure", "dropoff_arrival", "dropoff_completed",
                              "vehicle_number", "vehicle_supplier", "status", "expenses"]

            # Update the fields in the linked job to match the current document if they have values
            for field in fields_to_sync:
                if self.get(field):
                    linked_job.set(field, self.get(field))

            # Set a temporary flag in the linked job to prevent further recursion
            linked_job._is_syncing = True
            linked_job.save(ignore_permissions=True)
            del linked_job._is_syncing  # Remove the flag after save

            frappe.msgprint(f"Linked Road Job {linked_job_name} updated with changes from the current document.")
        
        # Clean up the flag after sync is done
        del self._is_syncing

@frappe.whitelist()
def link_container(container_number_to_link, self_container_number, job_type=None):
    try:
        # Retrieve container number based on container_number_to_link
        container_number = frappe.db.get_value("FPL Containers", {"name": container_number_to_link}, "container_number")
        
        # Find the FPLRoadJob that matches the container_number and job_type if specified
        filters = {"container_number": container_number}
        if job_type:
            filters["job_type"] = job_type
        
        road_jobs = frappe.get_all("FPLRoadJob", filters=filters, fields=["name"])
        
        if not road_jobs:
            return {"message": "No Job Order found with the specified container number."}

        # Link the container number to the first matching Road Job
        road_job_id = road_jobs[0].name

        # Retrieve the name of the container using self_container_number
        container_name = frappe.db.get_value("FPL Containers", {"container_number": self_container_number}, "name")

        # Set the container_number_to_link in FPLRoadJob to the container name
        frappe.db.set_value("FPLRoadJob", road_job_id, "container_number_to_link", container_name)

        # Update the double_20_ field in the Road Job
        frappe.db.set_value("FPLRoadJob", road_job_id, "double_20_", 1)

        return {"message": f"Road Job {road_job_id} updated with double_20_ set to 1."}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in link_container")
        return {"message": f"An error occurred: {str(e)}"}



