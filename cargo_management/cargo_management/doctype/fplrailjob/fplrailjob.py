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
        job_start_location: DF.Link | None
        job_type: DF.Link | None
        sales_order_number: DF.Data | None
        status: DF.Literal["", "Draft", "Assigned", "Completed", "Cancelled"]
        train_arrival_datetime: DF.Datetime | None
        train_number: DF.Link | None
    # end: auto-generated types

    def validate(self):
        if self.train_number:
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
            if next_job.job_name == "enrhva2nvi":
                yard_job = frappe.get_doc("FPLYardJob", next_job.job_id)
                yard_job.gate_in = self.train_arrival_datetime
                yard_job.save(ignore_permissions=True)
