from frappe.model.document import Document
import frappe

class FPLFreightOrders(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from cargo_management.cargo_management.doctype.fpl_jobs.fpl_jobs import FPLJobs
        from frappe.types import DF

        bounded: DF.Check
        client: DF.Link | None
        container_number: DF.Data | None
        container_type: DF.Link | None
        documents_received: DF.Datetime | None
        freight_order_number: DF.Data | None
        jobs: DF.Table[FPLJobs]
        last_job: DF.Data | None
        mm_completed_: DF.Check
        next_job: DF.Data | None
        sales_order_number: DF.Data | None
        seal_no: DF.Data | None
        size: DF.Int
        status: DF.Literal["", "Draft", "Cross Stuff", "In Progress", "Completed"]
        weight: DF.Float
    # end: auto-generated types

    def validate(self):
        self.check_job_status()
        if self.container_number and self.container_type:
            self.create_or_update_container()
            

    def after_insert(self):
        self.process_jobs()

    def check_job_status(self):
        if not self.jobs:
            self.status = 'Draft'
            return

        statuses = [job.status for job in self.jobs]
        
        if all(status == 'Completed' for status in statuses):
            self.status = 'Completed'
        elif all(status == 'Draft' for status in statuses):
            self.status = 'Draft'
        elif 'Completed' in statuses:
            self.status = 'In Progress'
        else:
            self.status = 'In Progress'    

    @frappe.whitelist()
    def process_jobs(self):
        for job in self.get("jobs"):
            service_type_doc = frappe.get_value("Service Type", {"name": job.job_name}, ["*"], as_dict=True)
            if service_type_doc:
                job_type = service_type_doc.get("job_type")
                if job_type == 'Rail':
                    self.create_fpl_rail_job(job, service_type_doc)
                elif job_type == 'Road':
                    self.create_fpl_road_job(job, service_type_doc) 
                elif job_type == 'Yard':
                    self.create_fpl_yard_job(job, service_type_doc)
                elif job_type == 'Cross Stuff':
                    self.create_fpl_CrossStuff_job(job, service_type_doc)    
                else:
                    frappe.msgprint(f"Job type for {job.job_name} is not specified.")
            else:
                frappe.msgprint(f"No Service Type found for job {job.job_name}")

    def create_fpl_CrossStuff_job(self, job, service_type_doc):
        crossStuff_job = frappe.get_doc({
            'doctype': 'FPLCrossStuffJob',
            'freight_order_id': self.freight_order_number,
            'job_type': service_type_doc['name'],
            'status': 'Draft',
            'sales_order_number': self.sales_order_number,
            'client': self.client,
            'cross_stuff_performance_location': job.start_location,
        })
        crossStuff_job.insert()       
        job.job_id = crossStuff_job.name
        # frappe.msgprint(f"Created Cross Stuff Job for {job.job_name}")            

    def create_fpl_rail_job(self, job, service_type_doc):
        rail_job = frappe.get_doc({
            'doctype': 'FPLRailJob',
            'freight_order_id': self.freight_order_number,
            'job_type': service_type_doc['name'],
            'status': 'Draft',
            'sales_order_number': self.sales_order_number,
            'client': self.client,
            'job_start_location': job.start_location,
            'job_end_location': job.end_location,
        })
        rail_job.insert()
        job.job_id = rail_job.name
        # frappe.msgprint(f"Creating Rail Job for {job.job_name}")

    def create_fpl_road_job(self, job, service_type_doc):
        road_job = frappe.get_doc({
            'doctype': 'FPLRoadJob',
            'freight_order_id': self.freight_order_number,
            'job_type': service_type_doc['name'],
            'status': 'Draft',
            'sales_order_number': self.sales_order_number,
            'client': self.client,
            'job_start_location': job.start_location,
            'job_end_location': job.end_location,
        })
        road_job.insert()       
        job.job_id = road_job.name
        # frappe.msgprint(f"Created Road Job for {job.job_name}")

    def create_fpl_yard_job(self, job, service_type_doc):
        yard_job = frappe.get_doc({
            'doctype': 'FPLYardJob',
            'freight_order_id': self.freight_order_number,
            'job_type': service_type_doc['name'],
            'status': 'Draft',
            'sales_order_number': self.sales_order_number,
            'client': self.client,
            'job_start_location': job.start_location,
            'job_end_location': job.end_location,
        })
        yard_job.insert()  
        job.job_id = yard_job.name
        # frappe.msgprint(f"Created Yard Job for {job.job_name}")


    def create_or_update_container(self):
        existing_container = frappe.get_all('FPL Containers', filters={'container_number': self.container_number}, fields=['*'])

        if existing_container:
            return
            frappe.msgprint("Container already in use !")
            # container = existing_container
        else:
            container = frappe.new_doc('FPL Containers')
            container.container_number = self.container_number
        
        container.container_type = self.container_type
        container.status = "Filled"
        container.freight_order_id = self.name
        container.state = None
        container.active_job_id = self.jobs[0].job_id
        container.container_location = self.fetchLocationfromFOJobGrid()
        container.container_location = self.fetchNextLocationfromFOJobGrid()
        container.save()
        self.update_container_in_jobs()
        


    def fetchLocationfromFOJobGrid(self):
        if self.jobs and self.jobs[0].start_location:
            return self.jobs[0].start_location
        else:
            frappe.msgprint("No start location found in the first job entry.")
            return None  

    def fetchNextLocationfromFOJobGrid(self):
        if self.jobs and self.jobs[1].start_location:
            return self.jobs[1].start_location
        else:
            frappe.msgprint("No start location found in the second job entry.")
            return None         

    def update_container_in_jobs(self):
        job_doctypes = ['FPLRailJob', 'FPLRoadJob', 'FPLYardJob', 'FPLCrossStuffJob']
        for doctype in job_doctypes:
            jobs = frappe.get_all(doctype, filters={'freight_order_id': self.freight_order_number}, fields=['name'])
            for job in jobs:
                job_doc = frappe.get_doc(doctype, job.name)
                if hasattr(job_doc, 'container_number'):
                    job_doc.container_number = self.container_number
                    job_doc.status = "Assigned"
                    job_doc.save()
                    frappe.msgprint(f"Updated {doctype} {job.name} with container number {self.container_number}")
                else:
                    frappe.msgprint(f"{doctype} {job.name} does not have a 'container_number' field.")
        
        for job in self.jobs:
            job.status = "Assigned"

    def update_container_in_jobs(self):
        job_doctypes = ['FPLRailJob', 'FPLRoadJob', 'FPLYardJob', 'FPLCrossStuffJob']
        for doctype in job_doctypes:
            jobs = frappe.get_all(doctype, filters={'freight_order_id': self.freight_order_number}, fields=['name'])
            for job in jobs:
                job_doc = frappe.get_doc(doctype, job.name)
                if hasattr(job_doc, 'container_number') and job_doc.status != "Completed":
                    job_doc.container_number = self.container_number
                    job_doc.status = "Assigned"
                    job_doc.save()
                    frappe.msgprint(f"Updated {doctype} {job.name} with container number {self.container_number}")
                else:
                    frappe.msgprint(f"{doctype} {job.name} does not have a 'container_number' field.")
        
        for job in self.jobs:
            if job.status != "Completed":
                job.status = "Assigned"

@frappe.whitelist()
def create_Job_withoutId(docname):
    doc = frappe.get_doc("FPL Freight Orders", docname)
    for job in doc.get("jobs"):
        if job.job_id is None:
            service_type_doc = frappe.get_value("Service Type", {"name": job.job_name}, ["*"], as_dict=True)
            job.status = 'Draft'
            if service_type_doc:
                job_type = service_type_doc.get("job_type")
                if job_type == 'Rail':
                    doc.create_fpl_rail_job(job, service_type_doc)
                elif job_type == 'Road':
                    doc.create_fpl_road_job(job, service_type_doc)
                elif job_type == 'Yard':
                    doc.create_fpl_yard_job(job, service_type_doc)
                elif job_type == 'Cross Stuff':
                    doc.create_fpl_CrossStuff_job(job, service_type_doc)      
                else:
                    frappe.msgprint(f"Job type for {job.job_name} is not specified.")
            else:
                frappe.msgprint(f"No Service Type found for job {job.job_name}")
    doc.update_container_in_jobs()
    doc.save()
