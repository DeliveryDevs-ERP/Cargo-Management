from cargo_management.cargo_management.utils.Update_JOB_Container_FO_Status import updateJobStatus
from frappe.utils import now_datetime
from frappe.model.document import Document
import frappe
from frappe import _
from frappe.utils import getdate

from cargo_management.cargo_management.utils.api import create_invoice


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
        job_name: DF.Data | None
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
        self.validate_dates()
        if self.container_number and len(self.expenses) > 0:
            self.validate_expenses()
            
        if (self.vehicle_number and self.vehicle_supplier) and (self.pickup_arrival and self.pickup_departure) and (self.dropoff_arrival and self.dropoff_completed) and self.status != "Completed":
            if updateJobStatus(self.name, self.freight_order_id, self.container_number):
                self.status = "Completed"
                self.completeNextGateIn()
            else:
                self.completePrevGateOut() 
                if updateJobStatus(self.name, self.freight_order_id, self.container_number):
                    self.status = "Completed"
                
        if self.status == "Assigned":
            self.assigned_at = now_datetime()   
        
        self.create_purchase_invoice()
    
    def validate_expenses(self):
        # Retrieve the container name only if there's a linked container number and freight order ID
        if self.container_number and self.freight_order_id:
            container_name = frappe.get_value("FPL Containers", {
                "freight_order_id": self.freight_order_id,
                "container_number": self.container_number
            }, "name")
            # Check if container_name was successfully retrieved
            if container_name:
                # frappe.errprint(f"Length of expenses {len(self.expenses)}")
                # Iterate through expenses to set the container_number where not already set
                for expense in self.expenses:
                    if not expense.container_number:
                        expense.container_number = container_name

    def create_purchase_invoice(self):
        default_company = frappe.defaults.get_user_default("company")
        for expense in self.expenses:
            if expense.purchase_invoiced_created == 0:
                item = frappe.get_value("FPL Cost Type", expense.expense_type, 'item_id')
                BO = frappe.get_value("FPL Freight Orders",self.freight_order_id,'sales_order_number')
                if item:
                    code = create_invoice(
                        container_number=expense.container_number,
                        # train_no=self.rail_number,
                        # movement_type=self.movement_type,
                        Road = self.name,
                        FO= self.freight_order_id,
                        BO=BO,
                        # crm_bill_no=expense.name,
                        items=[{
                            "item_code": item,
                            "qty": 1,
                            "rate": expense.amount
                        }],
                        supplier=expense.client,
                        company=default_company
                    )
                    if code:
                        expense.purchase_invoiced_created = 1
                        expense.purchase_invoice_no = code

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

    def validate_dates(self):
        BO_date = frappe.get_value("Booking Order", {"name": self.sales_order_number}, "sales_order_date")

        if not BO_date:
            frappe.throw(_("Booking Order Date not found for Sales Order Number: {0}").format(self.sales_order_number))

        if (self.pickup_departure and getdate(self.pickup_departure) < getdate(BO_date)) or \
        (self.pickup_arrival and getdate(self.pickup_arrival) < getdate(BO_date)) or \
        (self.dropoff_completed and getdate(self.dropoff_completed) < getdate(BO_date)) or \
        (self.dropoff_arrival and getdate(self.dropoff_arrival) < getdate(BO_date)):
            frappe.throw(_("None of the dates (pickup departure, pickup arrival, dropoff completed, dropoff arrival) should be before the Booking Order date {0}.").format(BO_date))


    def completePrevGateOut(self):
        freight_order = frappe.get_doc("FPL Freight Orders", self.freight_order_id)
        jobs = freight_order.jobs  # Assuming 'jobs' is the child table of Freight Order containing job references
        # Find current job index
        current_job_index = next((index for (index, job) in enumerate(jobs) if job.job_id == self.name), None)
        # Check if previous job is 'Gate Out' type
        if current_job_index is not None and current_job_index - 1 >= 0:
            previous_job = jobs[current_job_index - 1]
            if previous_job.job_name == "eo0ldr6jda":  # Assuming 'eo0ldr6jda' is a 'Gate Out' job name
                yard_job = frappe.get_doc("FPLYardJob", previous_job.job_id)
                yard_job.gate_out = self.pickup_departure  # Assuming 'pickup_departure' is the correct field for setting Gate Out time
                yard_job.save(ignore_permissions=True)
                
                    
    # def sync_with_linked_job(self):
    #     # Prevent recursion by setting a temporary flag
    #     if hasattr(self, "_is_syncing") and self._is_syncing:
    #         return
    #     self._is_syncing = True

    #     # Retrieve the container number based on container_number_to_link
    #     container_number = frappe.db.get_value("FPL Containers", {"name": self.container_number_to_link}, "container_number")

    #     # Get the name of the linked FPLRoadJob based on the container number and job type
    #     linked_job_name = frappe.db.get_value("FPLRoadJob", {"container_number": container_number, "job_type": self.job_type}, "name")

    #     if linked_job_name:
    #         linked_job = frappe.get_doc("FPLRoadJob", linked_job_name)

    #         # List of fields to sync
    #         fields_to_sync = ["pickup_arrival", "pickup_departure", "dropoff_arrival", "dropoff_completed",
    #                         "vehicle_number", "vehicle_supplier"]

    #         # Update the fields in the linked job to match the current document if they have values
    #         for field in fields_to_sync:
    #             if self.get(field):
    #                 linked_job.set(field, self.get(field))

    #         # Sync expenses separately without altering container_number
    #         if self.expenses:
    #             # Clear existing expenses and add new ones
    #             linked_job.expenses = []
    #             for expense in self.expenses:
    #                 new_expense = frappe.get_doc("Expenses cdt", expense.name).as_dict()
    #                 # frappe.errprint(f" Fetched expenses from self , {new_expense}")
    #                 del new_expense["container_number"]
    #                 del new_expense["name"]
    #                 del new_expense["parent"]
    #                 # frappe.errprint(f" Fetched expenses from self after del , {new_expense}")
    #                 linked_job.append("expenses", new_expense)

    #         # Set a temporary flag in the linked job to prevent further recursion
    #         linked_job._is_syncing = True
    #         linked_job.save(ignore_permissions=True)
    #         del linked_job._is_syncing  # Remove the flag after save
            
    #     # Clean up the flag after sync is done
    #     del self._is_syncing

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
            return {"message": "No Road Job found with the specified container number."}

        # Link the container number to the first matching Road Job
        road_job_id = road_jobs[0].name

        # Retrieve the name of the container using self_container_number
        container_name = frappe.db.get_value("FPL Containers", {"container_number": self_container_number}, "name")

        # Set the container_number_to_link in FPLRoadJob to the container name
        frappe.db.set_value("FPLRoadJob", road_job_id, "container_number_to_link", container_name)

        # Update the double_20_ field in the Road Job
        frappe.db.set_value("FPLRoadJob", road_job_id, "double_20_", 1)

        return 
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in link_container")
        return {"message": f"An error occurred: {str(e)}"}


@frappe.whitelist()
def sync_with_linked_job(docname):
    
    self = frappe.get_doc("FPLRoadJob",docname)
    # Prevent recursion by setting a temporary flag
    # if hasattr(self, "_is_syncing") and self._is_syncing:
    #     return
    # self._is_syncing = True

    # Retrieve the container number based on container_number_to_link
    container_number = frappe.db.get_value("FPL Containers", {"name": self.container_number_to_link}, "container_number")

    # Get the name of the linked FPLRoadJob based on the container number and job type
    linked_job_name = frappe.db.get_value("FPLRoadJob", {"container_number": container_number, "job_type": self.job_type}, "name")

    if linked_job_name:
        linked_job = frappe.get_doc("FPLRoadJob", linked_job_name)

        # List of fields to sync
        fields_to_sync = ["pickup_arrival", "pickup_departure", "dropoff_arrival", "dropoff_completed",
                        "vehicle_number", "vehicle_supplier"]

        # Update the fields in the linked job to match the current document if they have values
        for field in fields_to_sync:
            if self.get(field):
                linked_job.set(field, self.get(field))

        # Sync expenses separately without altering container_number
        if self.expenses:
            # Clear existing expenses and add new ones
            existing_expenses = {(expense.client, expense.expense_type, expense.amount) for expense in linked_job.expenses}
            for expense in self.expenses:
                new_expense = frappe.get_doc("Expenses cdt", expense.name).as_dict()
                # frappe.errprint(f" Fetched expenses from self , {new_expense}")
                del new_expense["container_number"]
                del new_expense["name"]
                del new_expense["parent"]
                del new_expense["purchase_invoiced_created"]
                del new_expense["purchase_invoice_no"]
                # frappe.errprint(f" Fetched expenses from self after del , {new_expense}")
                expense_key = (new_expense.get("client"), new_expense.get("expense_type"), new_expense.get("amount"))
                if expense_key not in existing_expenses:
                    linked_job.append("expenses", new_expense)
                    existing_expenses.add(expense_key)
        # Set a temporary flag in the linked job to prevent further recursion
        linked_job._is_syncing = True
        linked_job.save(ignore_permissions=True)
        # del linked_job._is_syncing  # Remove the flag after save
            
    # Clean up the flag after sync is done
    # del self._is_syncing
    
