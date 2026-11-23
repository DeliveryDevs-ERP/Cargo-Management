from frappe.model.document import Document
import frappe
from frappe import _
import re
from frappe.utils import now

class ContainerNumberFormatError(frappe.ValidationError):
	pass

class ContainerWeightError(frappe.ValidationError):
	pass


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
        status: DF.Literal["", "Draft", "Assigned", "Cross Stuff", "In Progress", "Completed"]
        weight: DF.Float
    # end: auto-generated types

    def validate(self):
        self.validate_job_lineage()
        self.check_job_status()
        self.verify_job_location_status()
        if self.container_number and self.container_type and self.documents_received:
            self.validate_container_Number()
            self.create_or_update_container()
            if self.status == "Draft":
                self.status = "Assigned"
    
    def after_delete(self):
        # frappe.errprint(f"After Delete Called")
        if self.status == "Draft":
            self.delete_all_jobs_for_this_fo()
        elif self.status == "Assigned":
            frappe.msgprint("This FO has a container already assigned to it")
            self.delete_all_jobs_for_this_fo()
            self.delete_container_doc()
        elif self.status in ["In Progress", "Completed"] :
            if self.has_jobs_for_this_fo():
                frappe.throw(_("This Freight Order cannot be deleted, Please delete all the linked Jobs first"))       
            else:
                self.delete_container_doc()
                    
                
    def validate_container_Number(self):
        import re
        pattern = r'^[A-Z]{4}\d{7}$'
        if not re.match(pattern, self.container_number):
            frappe.throw(_("Container number must be 4 uppercase letters followed by 7 digits."),exc=ContainerNumberFormatError,)            
    
    def validate_job_lineage(self):
        old=self.get_doc_before_save()
        if old and any(self.get(key)!=old.get(key) for key in ('sales_order_number','freight_order_number')):
            frappe.throw(_('Saved Cargo Freight Order and Booking identities cannot be reassigned.'))
        prior={row.name:row for row in old.jobs} if old else {}
        kinds={'Road':'FPLRoadJob','Rail':'FPLRailJob','Yard':'FPLYardJob','Cross Stuff':'FPLCrossStuffJob'}
        seen=set()
        for row in self.jobs:
            previous=prior.get(row.name)
            if row.get('cargo_transfer') and row.get('cargo_transfer')!=(previous.get('cargo_transfer') if previous else None):
                if row.cargo_transfer!=frappe.flags.get('cargo_active_transfer'):
                    frappe.throw(_('Freight replacement provenance requires the active server-owned transfer.'))
            if not row.job_id:continue
            kind=kinds.get(frappe.db.get_value('Service Type',row.job_name,'job_type'))
            actual=frappe.db.get_value(kind,row.job_id,['freight_order_id','sales_order_number','job_type'],as_dict=True) if kind else None
            if not actual or (actual.freight_order_id,actual.sales_order_number,actual.job_type)!=(self.name,self.sales_order_number,row.job_name):
                frappe.throw(_('Cargo job reference belongs to another Freight Order, Booking or service.'))
            if (kind,row.job_id) in seen:
                frappe.throw(_('A Cargo job cannot occupy two Freight Order sequence positions.'))
            seen.add((kind,row.job_id))

    def after_insert(self):
        self.process_jobs()
        # Child rows were inserted before after_insert. Persist the generated
        # job references inside this same transaction, including direct inserts.
        for job in self.jobs:
            job.db_update()

    def check_job_status(self):
        if not self.jobs:
            self.status = 'Draft'
            return

        statuses = [job.status for job in self.jobs]
        if all(status == 'Completed' for status in statuses):
            self.status = 'Completed'
        elif any(status == 'Completed' for status in statuses):
            self.status = 'In Progress'
        elif all(status in ('Draft', 'Assigned') for status in statuses) and 'Assigned' in statuses:
            self.status = 'Assigned'
        elif all(status == 'Draft' for status in statuses):
            self.status = 'Draft'
        else:
            frappe.throw(_("Error finding status."))
            self.status = 'In Progress'
            
            
    @frappe.whitelist()
    def process_jobs(self):
        self.check_permission('write')
        frappe.db.sql('SELECT name FROM `tabFPL Freight Orders` WHERE name=%s FOR UPDATE',self.name)
        for job in self.get("jobs"):
            stored=frappe.db.get_value('FPL Jobs',job.name,['parent','job_name','job_id'],as_dict=True,for_update=True)
            if not stored or stored.parent!=self.name or stored.job_name!=job.job_name:
                frappe.throw(_('Save and verify the Freight Order job rows before generating jobs.'))
            if stored.job_id:
                job.job_id=stored.job_id
                continue
            if job.job_id:
                frappe.throw(_('Unpersisted Cargo job references cannot be supplied by the caller.'))
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
            job.db_update()

    def create_fpl_CrossStuff_job(self, job, service_type_doc):
        crossStuff_job = frappe.get_doc({
            'doctype': 'FPLCrossStuffJob',
            'cargo_transfer': job.get('cargo_transfer'),
            'freight_order_id': self.freight_order_number,
            'job_type': service_type_doc['name'],
            'status': 'Draft',
            'sales_order_number': self.sales_order_number,
            'client': self.client,
            'cross_stuff_performance_location': job.start_location,
            'assigned_at' : now()
        })
        crossStuff_job.insert()       
        job.job_id = crossStuff_job.name
        # frappe.msgprint(f"Created Cross Stuff Job for {job.job_name}")            

    def create_fpl_rail_job(self, job, service_type_doc):
        rail_job = frappe.get_doc({
            'doctype': 'FPLRailJob',
            'cargo_transfer': job.get('cargo_transfer'),
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
            'cargo_transfer': job.get('cargo_transfer'),
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
            'cargo_transfer': job.get('cargo_transfer'),
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
        
        max_weight = frappe.get_value("Container Type", self.container_type, "max_cargo_weight_kg")
        if self.weight > max_weight:
            frappe.throw(_(f"Container Weight must be less than {max_weight}."),exc=ContainerWeightError,) 
            return
        
        existing_container = frappe.get_all('FPL Containers', filters={'container_number': self.container_number, "freight_order_id": self.name}, fields=['*'])

        if not existing_container: # will be called only once on creation
            container = frappe.new_doc('FPL Containers')
            container.container_number = self.container_number
            container.container_type = self.container_type
            if self.name.split("-")[0] == "CFO":
                container.status = "Empty"
            else:
                container.status = "Filled"
            container.freight_order_id = self.name
            container.booking_order_id = self.sales_order_number
            container.state = None
            container.active_job_id = self.jobs[0].job_id
            container.container_location = self.fetchLocationfromFOJobGrid()
            container.container_next_location = self.fetchNextLocationfromFOJobGrid()
            container.save()
            self.update_container_in_jobs()
           


    def fetchLocationfromFOJobGrid(self):
        if self.jobs and self.jobs[0].start_location:
            return self.jobs[0].start_location
        else:
            frappe.msgprint("No start location found in the first job entry.")
            return None  

    def fetchNextLocationfromFOJobGrid(self):
        if self.jobs and len(self.jobs) > 1 and self.jobs[1].start_location:
            return self.jobs[1].start_location
        elif self.jobs and len(self.jobs) == 1 and self.jobs[0].end_location:
            return self.jobs[0].end_location
        else:
            frappe.msgprint("No start location found in the second job nor end location in first job entry.")
            return None         

    # def update_container_in_jobs(self):
    #     job_doctypes = ['FPLRailJob', 'FPLRoadJob', 'FPLYardJob', 'FPLCrossStuffJob']
    #     for doctype in job_doctypes:
    #         jobs = frappe.get_all(doctype, filters={'freight_order_id': self.freight_order_number}, fields=['name'])
    #         for job in jobs:
    #             job_doc = frappe.get_doc(doctype, job.name)
    #             if hasattr(job_doc, 'container_number'):
    #                 job_doc.container_number = self.container_number
    #                 job_doc.status = "Assigned"
    #                 job_doc.save()

        
    #     for job in self.jobs:
    #         job.status = "Assigned"

    def update_container_in_jobs(self):
        if not (self.container_number and self.container_type and self.documents_received):
            return
        job_doctypes = ['FPLRailJob', 'FPLRoadJob', 'FPLYardJob', 'FPLCrossStuffJob']
        for doctype in job_doctypes:
            jobs = frappe.get_all(doctype, filters={'freight_order_id': self.freight_order_number}, fields=['name'])
            for job in jobs:
                job_doc = frappe.get_doc(doctype, job.name)
                if hasattr(job_doc, 'container_number') and job_doc.status != "Completed" and not job_doc.get('cargo_retired'):
                    job_doc.container_number = self.container_number
                    job_doc.status = "Assigned"
                    job_doc.save()
        
        for job in self.jobs:
            if job.status != "Completed":
                job.status = "Assigned"
                
    def has_jobs_for_this_fo(self):
        job_doctypes = ['FPLRailJob', 'FPLYardJob', 'FPLRoadJob', 'FPLCrossStuffJob']
        for doctype in job_doctypes:
            # Check if there are any jobs associated with this Freight Order
            jobs = frappe.get_all(doctype, filters={'freight_order_id': self.name}, fields=['name'])
            if jobs:
                return True  # Return True immediately when jobs are found
        return False              
                
    def delete_all_jobs_for_this_fo(self):
        job_doctypes = ['FPLRailJob', 'FPLYardJob', 'FPLRoadJob', 'FPLCrossStuffJob']
        for doctype in job_doctypes:
            jobs = frappe.get_all(doctype, filters={'freight_order_id': self.name}, fields=['name'])
            for job in jobs:
                frappe.delete_doc(doctype, job.name)
                # frappe.msgprint(f"{doctype} job {job.name} associated with this Freight Order has been deleted.")

    def delete_container_doc(self):
        containers = frappe.get_all('FPL Containers', filters={'freight_order_id': self.name}, fields=['name'])
        for container in containers:
            frappe.delete_doc('FPL Containers', container.name)
            # frappe.msgprint(f"Container {container.name} associated with this Freight Order has been deleted.")            

    def verify_job_location_status(self):
        job_doctypes = ['FPLRailJob', 'FPLYardJob', 'FPLRoadJob', 'FPLCrossStuffJob']
        job_documents = {}

        for doctype in job_doctypes:
            docs = frappe.get_all(doctype, filters={'freight_order_id': self.name}, fields=["*"])
            for doc in docs:
                job_documents[doc.name] = (doctype, doc)

        # Check and update locations based on the jobs child table
        for job_entry in self.jobs:
            if job_entry.job_id in job_documents:
                job_doc_type, job_doc = job_documents[job_entry.job_id]
                location_update = False

                # Verify start location
                if job_doc.job_start_location != job_entry.start_location:
                    job_doc.job_start_location = job_entry.start_location
                    location_update = True

                # Verify end location if applicable
                if hasattr(job_doc, 'job_end_location') and job_doc.job_end_location != job_entry.end_location:
                    job_doc.job_end_location = job_entry.end_location
                    location_update = True

                # Save the job document if any updates are made
                if location_update:
                    frappe.get_doc(job_doc_type, job_doc.name).update({
                        'job_start_location': job_entry.start_location,
                        'job_end_location': job_entry.end_location
                    }).save()

@frappe.whitelist()
def create_Job_withoutId(docname):
    doc = frappe.get_doc("FPL Freight Orders", docname, for_update=True)
    doc.check_permission('write')
    frappe.db.sql('SELECT name FROM `tabFPL Freight Orders` WHERE name=%s FOR UPDATE',docname)
    for job in doc.get("jobs"):
        if not job.job_id:
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


@frappe.whitelist()
def change_container_number(freight_order_id, new_container_number):
    # Validate container number format
    pattern = r'^[A-Z]{4}\d{7}$'
    if not re.match(pattern, new_container_number):
        frappe.throw(_("Container number must be 4 uppercase letters followed by 7 digits."))

    freight_order = frappe.get_doc("FPL Freight Orders", freight_order_id)
    freight_order.check_permission('write')

    container = frappe.get_doc("FPL Containers", {
        "freight_order_id": freight_order_id,
        "container_type": freight_order.container_type,
        "booking_order_id": freight_order.sales_order_number
    })

    if not container:
        frappe.throw(_("No matching container found for this Freight Order."))

    # Update container number
    old_container_number = container.container_number
    container.container_number = new_container_number
    container.save()
    
    freight_order.container_number = new_container_number
    freight_order.save()

    # Update related jobs
    job_doctypes = ["FPLRoadJob", "FPLYardJob", "FPLRailJob", "FPLCrossStuffJob"]

    for doctype in job_doctypes:
        jobs = frappe.get_all(doctype, filters={"container_number": old_container_number, "freight_order_id": freight_order_id}, fields=["name"])
        for job in jobs:
            job_doc = frappe.get_doc(doctype, job.name)
            job_doc.container_number = new_container_number
            job_doc.save()

    return True
