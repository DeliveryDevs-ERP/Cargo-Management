# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _
from cargo_management.cargo_management.utils.Update_JOB_Container_FO_Status import updateJobStatus
from cargo_management.cargo_management.utils.getJobTypebyID import get_job_type_by_id


class FPLPerformMiddleMile(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from cargo_management.cargo_management.doctype.expenses_cdt.expenses_cdt import Expensescdt
        from cargo_management.cargo_management.doctype.fpl_mm_cdt.fpl_mm_cdt import FPLMMcdt
        from cargo_management.cargo_management.doctype.fpl_wagon_cdt.fpl_wagon_cdt import FPLWagoncdt
        from cargo_management.cargo_management.doctype.new_mm_cdt.new_mm_cdt import NewMMcdt
        from frappe.types import DF

        actual_arrival_datetime: DF.Datetime | None
        arrival_location: DF.Link | None
        break_number: DF.Data | None
        departure_location: DF.Link | None
        departure_time: DF.Datetime | None
        expected_departure_time_eda: DF.Datetime | None
        expected_time_of_arrival_eta: DF.Datetime | None
        expenses: DF.Table[Expensescdt]
        finish_arrival: DF.Check
        finish_departure: DF.Check
        finish_loading: DF.Check
        finish_train_formation: DF.Check
        loading_end_time: DF.Datetime | None
        loading_time: DF.Datetime | None
        loco_number: DF.Data | None
        middle_mile: DF.Table[FPLMMcdt]
        middle_mile_copy: DF.Table[NewMMcdt]
        middle_mile_in_loading: DF.Table[FPLMMcdt]
        movement_type: DF.Literal["", "Up", "Down"]
        offloading_end_time: DF.Datetime | None
        offloading_start_time: DF.Datetime | None
        rail_number: DF.Data
        status: DF.Literal["", "Train Formed", "Loaded", "Departed", "Arrived"]
        wagons: DF.Table[FPLWagoncdt]
    # end: auto-generated types

    def validate(self):
        self.validate_expected_dates()
        
        if self.finish_train_formation == 1 and self.finish_loading == 0: # formation is completed now completing loading
            self.fill_child_middle_mile_tables_with_WagonName_rows()
            # self.status = "Train Formed"
        
        if self.finish_train_formation == 1 and self.finish_loading == 1 and self.finish_departure == 0: # formation & loading is completed now completing departure
            self.carry_forward_the_specified_rows()    
            # self.status = "Loaded"

        if self.finish_train_formation == 1 and self.finish_loading == 1 and self.finish_departure == 1 and self.finish_arrival==0: # formation, loading & departure is completed now completing arrival
            self.carry_forward_the_specified_row2()
            self.update_gate_out_jobs() # do gate out job
            # self.bulk_update_container_status() # arrival completes
            
        if self.finish_arrival==1:
            self.bulk_update_container_status()


    def fill_child_middle_mile_tables_with_WagonName_rows(self): # Loading of Containers
        for wagon in self.get('wagons'):
            wagon_doc = frappe.get_doc('FPL Wagons', wagon.wagon_type)
            max_count = wagon_doc.max_count if wagon_doc else 0
            for _ in range(max_count):
                self.append('middle_mile', {
                    'wagon_number': wagon.wagon_number,
                    'job': 'Middle Mile',
                    'mm_job_id': None,  
                    'received_': 0,  
                    'container': None,  
                    'read_only': False  
                })

    def carry_forward_the_specified_rows(self): # Departure of containers
        middle_mile_rows = self.get('middle_mile')
        filtered_rows = [row for row in middle_mile_rows if row.container and row.wagon_number]
        for row in filtered_rows:
            self.append('middle_mile_in_loading', {
                'wagon_number': row.wagon_number,
                'job': row.job,
                'mm_job_id': row.mm_job_id,
                'received_': row.received_,
                'container': row.container,
                'read_only': True  
            })

    def carry_forward_the_specified_row2(self):
        middle_mile_rows = self.get('middle_mile_in_loading')
        for row in middle_mile_rows:
            self.append('middle_mile_copy', {
                'wagon_number': row.wagon_number,
                'job': row.job,
                'mm_job_id': row.mm_job_id,
                'received_': row.received_,
                'container': row.container,
                'read_only': False  
            })
    
    def bulk_update_container_status(self):
        for row in self.middle_mile_copy:
            if row.container:
                # Retrieve Freight Order and Job IDs based on container number
                container_number = frappe.db.get_value("FPL Containers", {"name": row.container}, "container_number")
                freight_order_id = frappe.db.get_value("FPL Freight Orders", {"container_number": container_number}, "name")
                mm_job_id = frappe.db.get_value("FPLRailJob", {"container_number": container_number}, "name")

                #frappe.msgprint(f"Processing container: {container_number}")
                #frappe.msgprint(f"Freight Order ID: {freight_order_id}, Middle Mile Job ID: {mm_job_id}")

                if freight_order_id and mm_job_id:
                    # Update job status as needed
                    frappe.db.set_value("FPLRailJob",mm_job_id,"train_number",self.name)
                    frappe.db.set_value("FPLRailJob",mm_job_id,"train_arrival_datetime",self.actual_arrival_datetime)
                    updateJobStatus(mm_job_id, freight_order_id, container_number)
                    rail_job_doc = frappe.get_doc("FPLRailJob", mm_job_id)
                    rail_job_doc.save()
                    # frappe.msgprint(f"Updated status for Middle Mile job: {mm_job_id}")

                    # Fetch the freight order document and locate "Middle Mile" job
                    freight_order = frappe.get_doc("FPL Freight Orders", freight_order_id)
                    middle_mile_index = None
                    middle_mile_job_end_location = None

                    # Find the index and end location of the "Middle Mile" job
                    for i, job in enumerate(freight_order.jobs):
                        if job.job_id == mm_job_id:
                            middle_mile_index = i
                            middle_mile_job_end_location = job.end_location
                            #frappe.msgprint(f"Found 'Middle Mile' job at index {middle_mile_index} with end location: {middle_mile_job_end_location}")
                            break

                    if middle_mile_index is not None and middle_mile_job_end_location:
                        # Retrieve "Gate In" and "Gate Out" service type names
                        gate_in_type_name = frappe.get_value("Service Type", {"name1": "Gate In"}, "name")
                        gate_out_type_name = frappe.get_value("Service Type", {"name1": "Gate Out"}, "name")

                        # Prepare the "Gate In" job document with an initial status of "Draft"
                        gate_in_job = frappe.get_doc({
                            'doctype': 'FPLYardJob',
                            'freight_order_id': freight_order_id,
                            'job_type': gate_in_type_name,
                            'status': 'Assigned',
                            'sales_order_number': freight_order.sales_order_number,
                            'client': freight_order.client,
                            'job_start_location': middle_mile_job_end_location,
                            'job_end_location': middle_mile_job_end_location,
                            'container_number': container_number
                        })
                        gate_in_job.insert()
                        #frappe.msgprint(f"Inserted 'Gate In' job with ID: {gate_in_job.name}")

                        # Append "Gate In" to the jobs table as a Document object after "Middle Mile"
                        gate_in_job_row = freight_order.append("jobs", {
                            "job_name": gate_in_type_name,  # Use valid job type name
                            "job_id": gate_in_job.name,
                            "status": "Assigned",
                            "start_location": middle_mile_job_end_location,
                            "end_location": middle_mile_job_end_location
                        })

                        # Prepare the "Gate Out" job document with status as "Draft"
                        gate_out_job = frappe.get_doc({
                            'doctype': 'FPLYardJob',
                            'freight_order_id': freight_order_id,
                            'job_type': gate_out_type_name,
                            'status': 'Assigned',
                            'sales_order_number': freight_order.sales_order_number,
                            'client': freight_order.client,
                            'job_start_location': middle_mile_job_end_location,
                            'job_end_location': middle_mile_job_end_location,
                            'container_number': container_number
                        })
                        gate_out_job.insert()
                        #frappe.msgprint(f"Inserted 'Gate Out' job with ID: {gate_out_job.name}")

                        # Append "Gate Out" to the jobs table as a Document object after "Gate In"
                        gate_out_job_row = freight_order.append("jobs", {
                            "job_name": gate_out_type_name,  # Use valid job type name
                            "job_id": gate_out_job.name,
                            "status": "Assigned",
                            "start_location": middle_mile_job_end_location,
                            "end_location": middle_mile_job_end_location
                        })

                        # Save the updated freight order with the new jobs
                        freight_order.mm_completed_ = 1
                        freight_order.save()
                        #frappe.msgprint(f"Freight order '{freight_order_id}' updated with 'Gate In' and 'Gate Out' jobs.")

                        freight_order.reload()
                        # Fix the freight order with the new jobs Order
                        self.fix_job_sequence_onGateInGateOut_insert(freight_order_id)

                        # Now complete the gate in job
                        gate_in_job.gate_in = self.actual_arrival_datetime
                        gate_in_job.save()
                        freight_order.reload()

    def fix_job_sequence_onGateInGateOut_insert(self, freight_order_id):
        # Fetch the freight order document
        freight_order = frappe.get_doc("FPL Freight Orders", freight_order_id)
        middle_mile_index = None
        gate_in_job = None
        gate_out_job = None
        gate_in_job_index = None

        # Log all jobs in the freight order
        #frappe.msgprint(f"Jobs in Freight Order '{freight_order_id}':")
        # for i, job in enumerate(freight_order.jobs):
        #     frappe.msgprint(f"Index {i}: Job Name - {job.job_name}, Job type - {get_job_type_by_id(job.job_id)}")

        # Identify Middle Mile, Gate In, and Gate Out jobs
        jobs_after_middle_mile = []
        for i, job in enumerate(freight_order.jobs):
            job_type = get_job_type_by_id(job.job_id)
            if job_type == "Middle Mile" and middle_mile_index is None:
                middle_mile_index = i
                #frappe.msgprint(f"Found 'Middle Mile' at index {middle_mile_index}")
            elif job_type == "Gate In" and middle_mile_index is not None and gate_in_job is None:
                gate_in_job = job
                gate_in_job_index = i
                #frappe.msgprint(f"Found 'Gate In' after 'Middle Mile' at index {i}")
            elif job_type == "Gate Out" and gate_in_job is not None:
                gate_out_job = job
                #frappe.msgprint(f"Found 'Gate Out' after 'Gate In' at index {i}")
            elif middle_mile_index is not None and gate_in_job is not None:
                jobs_after_middle_mile.append(job)

        # Confirm all necessary jobs were found
        if middle_mile_index is not None and gate_in_job and gate_out_job and gate_in_job_index is not None:
            # Temporarily hold jobs between "Middle Mile" and "Gate In" (exclusive of Gate In and Gate Out)
            tmp_jobs = freight_order.jobs[middle_mile_index + 1 : gate_in_job_index]

            #frappe.msgprint(f'Found {len(tmp_jobs)} temp jobs for reordering.')

            # Build the reordered list
            reordered_jobs = []
            reordered_jobs.extend(freight_order.jobs[:middle_mile_index + 1])  # Jobs up to "Middle Mile"
            reordered_jobs.append(gate_in_job)  # Insert "Gate In"
            reordered_jobs.append(gate_out_job)  # Insert "Gate Out"
            reordered_jobs.extend(tmp_jobs)  # Append jobs between "Middle Mile" and "Gate In"

            # Clear existing jobs and add reordered jobs with reset indices
            freight_order.set("jobs", [])
            for idx, job in enumerate(reordered_jobs, start=1):
                job.idx = idx  # Reset idx for each job
                freight_order.append("jobs", job.as_dict())

            # Save and reload to ensure changes reflect
            freight_order.save()
            freight_order.reload()
            #frappe.msgprint(f"Job sequence updated: 'Gate In' and 'Gate Out' placed after 'Middle Mile' in Freight Order '{freight_order_id}'.")
        
    def update_gate_out_jobs(self):
        for row in self.middle_mile_in_loading:
            if row.container:
                # Get the container number associated with the container ID
                container_number = frappe.db.get_value("FPL Containers", {"name": row.container}, "container_number")
                # Get the Freight Order ID associated with the container
                freight_order_id = frappe.db.get_value("FPL Freight Orders", {"container_number": container_number}, "name")

                if freight_order_id:
                    # Fetch the Freight Order document
                    freight_order = frappe.get_doc("FPL Freight Orders", freight_order_id)
                    needs_save = False  # Flag to indicate if save is needed

                    # First pass: Update all Middle Mile jobs to In Progress
                    for job in freight_order.jobs:
                        job_type = get_job_type_by_id(job.job_id)
                        if job_type == "Middle Mile" and job.status != "In Progress":
                            job.status = "In Progress"
                            needs_save = True  # Set flag to save changes

                    # Save changes if any Middle Mile jobs were updated
                    if needs_save:
                        freight_order.save()
                        frappe.db.commit()  # Commit changes to ensure Middle Mile statuses are updated

                    # Second pass: Process Gate Out jobs
                    for job in freight_order.jobs:
                        job_type = get_job_type_by_id(job.job_id)
                        if job_type == "Gate Out":
                            try:
                                gate_out_job_doc = frappe.get_doc("FPLYardJob", job.job_id)
                                if not self.departure_time:
                                    frappe.msgprint("Departure time is not set.")
                                    return

                                gate_out_job_doc.gate_out = self.departure_time
                                gate_out_job_doc.save()
                                frappe.db.commit()  # Commit each Gate Out job update individually

                            except Exception as e:
                                frappe.msgprint(f"Error updating Gate Out job {job.job_id} for container {row.container}: {str(e)}")

                        
    def validate_expected_dates(self):
        if self.expected_departure_time_eda and self.expected_time_of_arrival_eta:
            if self.expected_time_of_arrival_eta < self.expected_departure_time_eda:
                frappe.throw(_("The expected time of arrival (ETA) cannot be before the expected departure time (EDA)."))

                    
