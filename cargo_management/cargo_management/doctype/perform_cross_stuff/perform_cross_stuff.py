import frappe
from frappe.model.document import Document

from cargo_management.cargo_management.doctype.fpl_freight_orders.fpl_freight_orders import create_Job_withoutId

class PerformCrossStuff(Document):
    def on_submit(self):
        temp_jobs = self.amend_FOs()
        frappe.msgprint(f"length of temp Job after: {len(temp_jobs)}")
        temp_jobs = self.remove_jobIds(temp_jobs)
        frappe.msgprint(f"length of temp Job before: {len(temp_jobs)}")
        self.amend_CFOs(temp_jobs)

    def amend_FOs(self):
        temp_jobs = []
        processed_containers = []
        cross_stuff_job_names = ["l645t4f4fm", "l6cdsvneqs"]
        for row in self.grounded_filled_containers:
            if row.container_number and row.container_number not in processed_containers:
                processed_containers.append(row.container_number)
                container_number = frappe.get_value("FPL Containers", {"name": row.container_number}, "container_number")
                frappe.db.set_value("FPL Containers", row.container_number, "status", "Empty")
                FO = frappe.get_doc("FPL Freight Orders", {"container_number": container_number})
                FO.status = "Cross Stuff"
                FO.weight = 0
                existing_cross_stuff_job_index = next((i for i, job in enumerate(FO.jobs) if job.job_name in cross_stuff_job_names), None)
                if existing_cross_stuff_job_index is not None:
                    temp_jobs.extend(FO.jobs[existing_cross_stuff_job_index:])
                    if FO.jobs[existing_cross_stuff_job_index - 1].job_name == 'eo0ldr6jda':
                        FO.jobs = FO.jobs[:existing_cross_stuff_job_index]
                    else:
                        FO.jobs = FO.jobs[:existing_cross_stuff_job_index]
                    self.append_Gate_Out_job(FO, existing_cross_stuff_job_index, row)
                    self.append_empty_return_job(FO, row)
                else:
                    job_to_amend_index = next((i for i, job in enumerate(FO.jobs) if job.job_name == self.job_before_cross_stuff), None)
                    if job_to_amend_index is not None:
                        crossStuff_location = FO.jobs[job_to_amend_index].start_location
                        temp_jobs.extend(FO.jobs[job_to_amend_index:])
                        if FO.jobs[job_to_amend_index - 1].job_name == 'eo0ldr6jda':
                            frappe.db.delete("FPLYardJob", {"name": FO.jobs[job_to_amend_index - 1].job_id})
                            FO.jobs = FO.jobs[:job_to_amend_index - 1]
                        else:
                            FO.jobs = FO.jobs[:job_to_amend_index]
                        self.append_cross_stuff_job(FO, crossStuff_location, row)
                        self.append_Gate_Out_job(FO, crossStuff_location, row)
                        self.append_empty_return_job(FO, row)

                # Reindex jobs to maintain sequential idx
                for idx, job in enumerate(FO.jobs, start=1):
                    job.idx = idx
                frappe.msgprint(f"Length of FO jobs {len(FO.jobs)}")
                FO.save()
                create_Job_withoutId(FO.name)
        return temp_jobs


    def append_empty_return_job(self, FO, row):
        transport_mode = self.determine_transport_mode()
        FO.append('jobs', {
            'job_name': self.get_service_type_name("Empty Return", transport_mode),
            'status': 'Draft',
            'start_location': self.grounded_yard_location,
            'end_location': row.empty_return_location
        })

    def append_Gate_Out_job(self, FO, crossStuff_location, row):
        transport_mode = self.determine_transport_mode()
        FO.append('jobs', {
            'job_name': self.get_service_type_name("Gate Out", transport_mode),
            'status': 'Draft',
            'start_location': crossStuff_location,
            'end_location': crossStuff_location
        })        

    def append_cross_stuff_job(self, FO, crossStuff_location, row):
        transport_mode = self.determine_transport_mode()
        FO.append('jobs', {
            'job_name': self.get_service_type_name("Cross Stuff", transport_mode),
            'status': 'Draft',
            'start_location': crossStuff_location,
            'end_location': None
        })

    def determine_transport_mode(self):
        rail_truck_jobs = ["giml5efmsh", "oasikqkqg2"]
        rail_train_jobs = ["oalds7gjs7", "oagb0ddmuo", "vg2osur4ei"]
        if self.job_before_cross_stuff in rail_truck_jobs:
            return "Rail (Truck)"
        elif self.job_before_cross_stuff in rail_train_jobs:
            return "Rail (Train)"
        return None

    def get_service_type_name(self, service_name, transport_mode):
        if service_name in ['Gate In', 'Gate Out']:
            service_type = frappe.get_value(
                "Service Type",
                {"name1": service_name},
                "name"
            )
        else:
            service_type = frappe.get_value(
                "Service Type",
                {"name1": service_name, "transport_mode": transport_mode},
                "name"
            )
        
        if service_type:
            return service_type
        else:
            frappe.throw(
                f"No Service Type found for name1: {service_name} and transport mode: {transport_mode}"
            )

    def remove_jobIds(self, Jobs):
        for job in Jobs: #Delete the Documents in respective documents
            if job.job_id:
                frappe.db.delete("FPLRoadJob", {"name": job.job_id})
                frappe.db.delete("FPLRailJob", {"name": job.job_id})
                frappe.db.delete("FPLYardJob", {"name": job.job_id})
                job.job_id = None
        return Jobs    

    def amend_CFOs(self, temp_jobs):
        processed_containers = []
        for row in self.grounded_filled_containers:
            if row.reference_container and row.reference_container not in processed_containers:
                processed_containers.append(row.reference_container)
                container_number = frappe.get_value("FPL Containers", {"name": row.reference_container}, "container_number")
                CFO = frappe.get_doc("FPL Freight Orders", {"container_number": container_number})
                # frappe.db.set_value("FPL Freight Orders",CFO.name, "weight", row.weight_to_transfer)
                # Append each job individually
                next_idx = len(CFO.jobs) + 1 
                for job in temp_jobs:
                    job.idx = next_idx
                    CFO.append('jobs', {
                        "job_name": job.job_name,
                        "status": job.status,
                        "start_location": job.start_location,
                        "end_location": job.end_location,
                        "idx": next_idx
                    })
                    next_idx += 1

                # Save the CFO document to persist changes
                CFO.save()
                frappe.msgprint(f"Length of CFO jobs {len(CFO.jobs)}")
                create_Job_withoutId(CFO.name)