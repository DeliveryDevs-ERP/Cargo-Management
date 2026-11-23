from cargo_management.cargo_management.utils.services import is_service, service_names
# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe

class FPLRailJob(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        assigned_at: DF.Datetime | None
        client: DF.Link | None
        container_number: DF.Data | None
        freight_order_id: DF.Data | None
        job_end_location: DF.Link | None
        job_name: DF.Data | None
        job_start_location: DF.Link | None
        job_type: DF.Link | None
        sales_order_number: DF.Data | None
        status: DF.Literal["", "Draft", "Assigned", "Completed", "Cancelled"]
        train_arrival_datetime: DF.Datetime | None
        train_number: DF.Link | None
    # end: auto-generated types

    def validate(self):
        if self.train_number:
            train=frappe.get_doc('FPL Perform Middle Mile',self.train_number)
            train.check_permission('read')
            if not self.flags.get('cargo_receipt_verified'):
                matched=[row for row in train.middle_mile_copy if row.received_
                         and frappe.db.get_value('FPL Containers',row.container,'freight_order_id')==self.freight_order_id]
                if not matched or not self.train_arrival_datetime:
                    frappe.throw('Rail job completion requires a verified received train allocation.')
            freight=frappe.get_doc('FPL Freight Orders',self.freight_order_id)
            child=next((row for row in freight.jobs if row.job_id==self.name),None)
            if not child or child.status!='Completed':
                if not updateJobStatus(self.name,self.freight_order_id,self.container_number):
                    frappe.throw('Rail job completion cannot bypass preceding jobs.')
            self.status = "Completed"
            self.completeNextGateIn()
   
    def completeNextGateIn(self):
        # Fetch the Freight Order associated with this Rail Job
        freight_order = frappe.get_doc("FPL Freight Orders", self.freight_order_id)
        jobs = freight_order.jobs 
        current_job_index = next((index for (index, job) in enumerate(jobs) if job.job_id == self.name), None)
        
        # Check if next job is 'Gate In' type
        if current_job_index is not None and current_job_index + 1 < len(jobs):
            next_job = jobs[current_job_index + 1]
            if is_service(next_job.job_name, "Gate In"):
                yard_job = frappe.get_doc("FPLYardJob", next_job.job_id)
                yard_job.gate_in = self.train_arrival_datetime
                yard_job.save()
