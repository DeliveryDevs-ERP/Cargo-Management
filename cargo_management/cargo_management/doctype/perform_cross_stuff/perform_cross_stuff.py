import frappe
from frappe.model.document import Document

from cargo_management.cargo_management.doctype.fpl_freight_orders.fpl_freight_orders import create_Job_withoutId
from cargo_management.cargo_management.utils.api import create_invoice

class PerformCrossStuff(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from cargo_management.cargo_management.doctype.expenses_cdt.expenses_cdt import Expensescdt
        from cargo_management.cargo_management.doctype.grounded_filled_cdt.grounded_filled_cdt import GroundedFilledCdt
        from frappe.types import DF

        amended_from: DF.Link | None
        booking_order_id: DF.Link | None
        date: DF.Datetime | None
        expenses: DF.Table[Expensescdt]
        grounded_filled_containers: DF.Table[GroundedFilledCdt]
        grounded_yard_location: DF.Link | None
        job_before_cross_stuff: DF.Link | None
        remaining_weight: DF.Float
        total_weight: DF.Float
    # end: auto-generated types
    def on_submit(self):
        temp_jobs = self.amend_FOs()
        # frappe.msgprint(f"length of temp Job after: {len(temp_jobs)}")
        #temp_jobs = list(set(temp_jobs))
        # frappe.errprint(f"Temp Jobs before : {temp_jobs}")
        temp_jobs = self.remove_jobIds(temp_jobs)
        # frappe.errprint(f"Temp Jobs after : {temp_jobs}")
        # frappe.msgprint(f"length of temp Job before: {len(temp_jobs)}")
        self.amend_CFOs(temp_jobs)
        self.complete_crossStuffJob_in_FO()
        self.change_empty_return_end_location_in_CFO()
        self.assign_performance_in_request()
        self.create_purchase_invoice()

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
                    self.append_empty_return_job(FO, crossStuff_location, row)
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
                        self.append_empty_return_job(FO, crossStuff_location, row)

                # Reindex jobs to maintain sequential idx
                for idx, job in enumerate(FO.jobs, start=1):
                    job.idx = idx
                # frappe.msgprint(f"Length of FO jobs {len(FO.jobs)}")
                FO.save()
                create_Job_withoutId(FO.name)
        return temp_jobs


    def append_empty_return_job(self, FO, crossStuff_location,  row):
        transport_mode = self.determine_transport_mode()
        FO.append('jobs', {
            'job_name': self.get_service_type_name("Empty Return", transport_mode),
            'status': 'Draft',
            'start_location': crossStuff_location,
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

    def create_purchase_invoice(self):
        default_company = frappe.defaults.get_user_default("company")
        for expense in self.expenses:
            if expense.purchase_invoiced_created == 0:
                item = frappe.get_value("FPL Cost Type", expense.expense_type, 'item_id')
                if item:
                    code = create_invoice(
                        container_number=expense.container_number,
                        FO=frappe.get_value("FPL Containers", expense.container_number, 'freight_order_id'),
                        BO = self.booking_order_id,
                        items=[{
                            "item_code": item,
                            "qty": 1,
                            "rate": expense.amount
                        }],
                        supplier=expense.client,
                        company=default_company
                    )
                    if code == True:
                        expense.purchase_invoiced_created = 1
                        
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
                FO_container_number = frappe.get_value("FPL Containers", {"name": row.container_number}, "container_number")
                frappe.db.set_value("FPL Containers", row.reference_container, "status", "Filled")
                CFO = frappe.get_doc("FPL Freight Orders", {"container_number": container_number})
                FO = frappe.get_value("FPL Freight Orders",{"sales_order_number":self.booking_order_id, "container_number": FO_container_number}, "name")
                FO_rate_type = frappe.get_value("FPL Freight Orders",{"sales_order_number":self.booking_order_id, "container_number": FO_container_number}, "rate_type")
                FO_rate = frappe.get_value("FPL Freight Orders",{"sales_order_number":self.booking_order_id, "container_number": FO_container_number}, "rate")
                # FO_weight = frappe.get_value("FPL Freight Orders",{"sales_order_number":self.booking_order_id, "container_number": FO_container_number}, "weight")
                FO_weight = row.weight
                CFO.rate_type = FO_rate_type
                next_idx = len(CFO.jobs) + 1 
                
                Per_weight_rate = 1
                if FO_rate_type == "Per Container":
                    Per_weight_rate = FO_rate / FO_weight 
                    
                for job in temp_jobs:
                    if job.parent == FO:
                        job.idx = next_idx
                        CFO.append('jobs', {
                            "job_name": job.job_name,
                            "status": job.status,
                            "start_location": job.start_location,
                            "end_location": job.end_location,
                            "idx": next_idx
                        })
                        next_idx += 1

                cum_weight = 0
                cum_bag = 0
                for row2 in self.grounded_filled_containers:
                    if row2.reference_container == row.reference_container:
                        cum_weight += row2.weight_to_transfer
                        cum_bag += row2.bags_to_transfer

                CFO.bag_qty = cum_bag
                CFO.weight = cum_weight
                if FO_rate_type == "Per Container":
                    CFO.rate = cum_weight * Per_weight_rate
                    CFO.rate_type = "Per Weight(Ton)"
                else:
                    CFO.rate = FO_rate
                    
                CFO.save()
                create_Job_withoutId(CFO.name)                
                    
    def complete_crossStuffJob_in_FO(self):
        for row in self.grounded_filled_containers:
            if row.container_number:
                container_number = frappe.get_value("FPL Containers", {"name": row.container_number}, "container_number")
                FO = frappe.get_doc("FPL Freight Orders", {"container_number": container_number})
                CrossStuff = frappe.get_doc("FPLCrossStuffJob", {"container_number": container_number, "freight_order_id": FO.name, "sales_order_number": self.booking_order_id})
                CrossStuff.performance_details = self.name
                CrossStuff.save()
    
    def change_empty_return_end_location_in_CFO(self):
        for row in self.grounded_filled_containers:
            if row.reference_container:
                container_number = frappe.get_value("FPL Containers", {"name": row.reference_container}, "container_number")
                CFO = frappe.get_doc("FPL Freight Orders", {"container_number": container_number})
                
                # Fetch the specific Empty Return job
                EmptyReturn =  frappe.get_list("FPLRoadJob", 
                    filters={
                        "container_number": container_number,
                        "freight_order_id": CFO.name,
                        "sales_order_number": self.booking_order_id,
                        "job_type": ["in", ["l5dbk4s5u4", "l5if4pva8b"]]
                    }, 
                    fields=["name"]
                )
                if EmptyReturn:
                    EmptyReturn = frappe.get_doc("FPLRoadJob", EmptyReturn[0].name)
                EmptyReturn.job_end_location = row.empty_return_location
                EmptyReturn.save()
                
                # Update the job end location in CFO.jobs grid
                for job in CFO.jobs:
                    if job.job_id == EmptyReturn.name:
                        job.end_location = row.empty_return_location
                        break
                
                # Save the changes to the CFO document
                CFO.save()


    # def assign_performance_in_request(self):
    #     requests = frappe.get_all("Container or Vehicle Request",
    #                             filters={
    #                                 "booking_order_id": self.booking_order_id,
    #                                 "cross_stuff_performance": ["is", "not set"],
    #                                 "docstatus": 1
    #                             },
    #                             fields=["name"])

    #     for request in requests:
    #         frappe.db.set_value("Container or Vehicle Request", request["name"], "cross_stuff_performance", self.name)
            
    #     frappe.db.commit()
    
    
    def assign_performance_in_request(self):
        ref_container_count = sum(1 for x in self.grounded_filled_containers if x.reference_container == row.reference_container)
        requests = frappe.get_all("Container or Vehicle Request",
                                filters={
                                    "booking_order_id": self.booking_order_id,
                                    "cross_stuff_performance": ["is", "not set"],
                                    "docstatus": 1
                                },
                                fields=["name", "table_ktch"])

        for request in requests:
            count_req = 0
            request_doc = frappe.get_doc("Container or Vehicle Request", request["name"])
            for row in request_doc.table_ktch:
                count_req += row.qty

            if ref_container_count == count_req:
                frappe.db.set_value("Container or Vehicle Request", request["name"], "cross_stuff_performance", self.name)
                frappe.db.commit()