from cargo_management.cargo_management.utils.services import is_service, service_names
from cargo_management.setup import get_account_manager_emails
import frappe
from frappe.model.document import Document

from cargo_management.cargo_management.doctype.fpl_freight_orders.fpl_freight_orders import create_Job_withoutId
from cargo_management.cargo_management.utils.api import create_invoice
from frappe.utils import getdate, get_link_to_form


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
    def before_submit(self):
        import uuid
        from cargo_management.cargo_management.utils.cross_stuff_history import prepare
        self.flags.cargo_cross_savepoint = 'cargo_cross_' + uuid.uuid4().hex[:12]
        frappe.db.savepoint(self.flags.cargo_cross_savepoint)
        try:
            prepare(self)
        except Exception:
            frappe.db.rollback(save_point=self.flags.cargo_cross_savepoint)
            frappe.flags.cargo_active_transfer = None
            raise

    def on_submit(self):
        existing = frappe.db.get_value('Cargo Cross Stuff Transfer', {'performance': self.name}, ['name', 'after_state', 'state'], as_dict=True)
        if existing and existing.after_state and existing.state == 'Applied':
            return
        try:
            return self.apply_transfer()
        except Exception:
            if self.flags.get('cargo_cross_savepoint'):
                frappe.db.rollback(save_point=self.flags.cargo_cross_savepoint)
            raise
        finally:
            frappe.flags.cargo_active_transfer = None

    def before_cancel(self):
        from cargo_management.cargo_management.utils.cross_stuff_history import reverse
        reverse(self)

    def apply_transfer(self):
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
        if len(self.expenses) > 0:
            self.send_expense_invoice_notification()
        from cargo_management.cargo_management.utils.cross_stuff_history import finish
        finish(self)

    def on_change(self):
        self.create_purchase_invoice()
        if len(self.expenses) > 0:
            self.send_expense_invoice_notification()


    def freight_for_container(self, container_record):
        freight = frappe.db.get_value('FPL Containers', container_record, 'freight_order_id') if container_record else None
        if not freight:
            frappe.throw('Selected container has no Freight Order reference.')
        return freight

    def amend_FOs(self):
        temp_jobs = []
        processed_containers = []
        cross_stuff_job_names = service_names("Cross Stuff")
        for row in self.grounded_filled_containers:
            if row.container_number and row.container_number not in processed_containers:
                processed_containers.append(row.container_number)
                container_number = frappe.get_value("FPL Containers", {"name": row.container_number}, "container_number")
                frappe.db.set_value("FPL Containers", row.container_number, "status", "Empty")
                FO = frappe.get_doc("FPL Freight Orders", self.freight_for_container(row.container_number))
                FO.status = "Cross Stuff"
                FO.weight = 0
                existing_cross_stuff_job_index = next((i for i, job in enumerate(FO.jobs) if job.job_name in cross_stuff_job_names), None)
                if existing_cross_stuff_job_index is not None:
                    crossStuff_location = FO.jobs[existing_cross_stuff_job_index].start_location
                    # Keep the source Cross-Stuff job: on_submit completes it.
                    # Only subsequent work transfers to the replacement CFO.
                    temp_jobs.extend(FO.jobs[existing_cross_stuff_job_index + 1:])
                    FO.jobs = FO.jobs[:existing_cross_stuff_job_index + 1]
                    self.append_Gate_Out_job(FO, crossStuff_location, row)
                    self.append_empty_return_job(FO, crossStuff_location, row)
                else:
                    job_to_amend_index = next((i for i, job in enumerate(FO.jobs) if job.job_name == self.job_before_cross_stuff), None)
                    if job_to_amend_index is not None:
                        crossStuff_location = FO.jobs[job_to_amend_index].start_location
                        temp_jobs.extend(FO.jobs[job_to_amend_index:])
                        if job_to_amend_index > 0 and is_service(FO.jobs[job_to_amend_index - 1].job_name, "Gate Out"):
                            self.flags.setdefault('cargo_discard_jobs', []).append(FO.jobs[job_to_amend_index - 1])
                            FO.jobs = FO.jobs[:job_to_amend_index - 1]
                        else:
                            FO.jobs = FO.jobs[:job_to_amend_index]
                        self.append_cross_stuff_job(FO, crossStuff_location, row)
                        self.append_Gate_Out_job(FO, crossStuff_location, row)
                        self.append_empty_return_job(FO, crossStuff_location, row)

                # Reindex jobs to maintain sequential idx
                for idx, job in enumerate(FO.jobs, start=1):
                    job.idx = idx
                # This FO already has its container. Apply the existing
                # assignment routine before validating a mix of retained and
                # newly appended jobs; job creation below repeats it safely.
                FO.update_container_in_jobs()
                # frappe.msgprint(f"Length of FO jobs {len(FO.jobs)}")
                FO.save()
                create_Job_withoutId(FO.name)
        return temp_jobs
    
    def send_expense_invoice_notification(self):
        booking_order = self.booking_order_id or frappe.db.get_value("FPL Containers", self.container_number, "booking_order_id")
        sales_order = frappe.db.get_value("Sales Order", {"custom_booking_order_id": booking_order}, "name")
        recipient_emails = get_account_manager_emails(booking_order)

        if not recipient_emails:
            frappe.msgprint("No Accounts Managers found with valid email addresses.")
            return

        pending_expenses = []
        for expense in self.expenses:
            if expense.invoiced_ == 1 and not expense.sales_invoice_no:
                pending_expenses.append(expense)

        if not pending_expenses:
            return  
        
        job_link = get_link_to_form("Perform Cross Stuff", self.name)

        rows = ""
        for expense in pending_expenses:
            rows += f"""
                <tr>
                    <td>{expense.expense_type}</td>
                    <td>{expense.amount}</td>
                </tr>
            """

        table_html = f"""
            <table class="panel-header" border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr height="10"></tr>
                <tr>
                    <td width="15"></td>
                    <td>
                        <div class="text-medium text-muted">
                            <h2>Please create Sales Invoice for Job: {self.name}</h2>
                        </div>
                    </td>
                    <td width="15"></td>
                </tr>
                <tr height="10"></tr>
            </table>

            <table class="panel-body" border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr height="10"></tr>
                <tr>
                    <td width="15"></td>
                    <td>
                        <div>
                            <ul class="list-unstyled" style="line-height: 1.7">
                                <li><b>Sales Order:</b> {sales_order}</li>
                                <li><b>Booking Order:</b> {booking_order}</li>
                                <li><b>Job Document:</b> {job_link}</li>
                            </ul>
                            <br>
                            <table border="1" cellpadding="5" cellspacing="0" style="width:100%; border-collapse: collapse;">
                                <thead style="background: #f0f0f0;">
                                    <tr>
                                        <th>Expense Type</th>
                                        <th>Amount</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows}
                                </tbody>
                            </table>
                        </div>
                    </td>
                    <td width="15"></td>
                </tr>
                <tr height="10"></tr>
            </table>
    """

        frappe.sendmail(
            recipients=recipient_emails,
            subject=f"Pending Sales Invoice for Job: {self.name}",
            message=table_html
        )

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
        rail_truck_jobs = ["Long Haul", "Short Haul", "Shifting"]
        rail_train_jobs = ["Last Mile", "Middle Mile", "First Mile"]
        label = frappe.db.get_value("Service Type", self.job_before_cross_stuff, "name1")
        if label in rail_truck_jobs:
            return "Road (Truck)"
        elif label in rail_train_jobs:
            return "Rail (Train)"
        return None

    def create_purchase_invoice(self):
        if not self.expenses:
            return
        from cargo_management.cargo_management.utils.configuration import booking_company
        default_company = booking_company(self.booking_order_id)
        for expense in self.expenses:
            if not expense.purchase_invoiced_created:
                item = frappe.get_value("FPL Cost Type", expense.expense_type, 'item_id')
                if item:
                    code = create_invoice(
                        container_number=expense.container_number,
                        FO=frappe.get_value("FPL Containers", expense.container_number, 'freight_order_id'),
                        BO = self.booking_order_id,
                        CS = self.name,
                        items=[{
                            "item_code": item,
                            "qty": 1,
                            "rate": expense.amount
                        }],
                        supplier=expense.client,
                        company=default_company
                    )
                    if code:
                        expense.purchase_invoice_no = code
                        expense.purchase_invoiced_created = 1
                        expense.save()
                        
                        
    def get_service_type_name(self, service_name, transport_mode):
        from cargo_management.cargo_management.utils.configuration import resolve_service, booking_company
        return resolve_service(service_name, transport_mode, booking_company(self.booking_order_id))

    def remove_jobIds(self, Jobs):
        from cargo_management.cargo_management.utils.cross_stuff_history import retire_or_delete
        retire_or_delete(self, self.flags.get('cargo_discard_jobs') or [])
        return retire_or_delete(self, Jobs)

    def amend_CFOs(self, temp_jobs):
        processed_containers = []
        for row in self.grounded_filled_containers:
            if row.reference_container and row.reference_container not in processed_containers:
                processed_containers.append(row.reference_container)
                container_number = frappe.get_value("FPL Containers", {"name": row.reference_container}, "container_number")
                FO_container_number = frappe.get_value("FPL Containers", {"name": row.container_number}, "container_number")
                frappe.db.set_value("FPL Containers", row.reference_container, "status", "Filled")
                CFO = frappe.get_doc("FPL Freight Orders", self.freight_for_container(row.reference_container))
                FO = self.freight_for_container(row.container_number)
                FO_rate_type = frappe.get_value("FPL Freight Orders", FO, "rate_type")
                FO_rate = frappe.get_value("FPL Freight Orders", FO, "rate")
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
                            ,"cargo_transfer": self.flags.cargo_transfer_journal.name
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
                    # CFO.rate_type = "Per Weight(Ton)"
                else:
                    CFO.rate = FO_rate
                    
                CFO.save()
                create_Job_withoutId(CFO.name)                
                    
    def complete_crossStuffJob_in_FO(self):
        for row in self.grounded_filled_containers:
            if row.container_number:
                container_number = frappe.get_value("FPL Containers", {"name": row.container_number}, "container_number")
                FO = frappe.get_doc("FPL Freight Orders", self.freight_for_container(row.container_number))
                CrossStuff = frappe.get_doc("FPLCrossStuffJob", {"container_number": container_number, "freight_order_id": FO.name, "sales_order_number": self.booking_order_id})
                CrossStuff.performance_details = self.name
                CrossStuff.save()
    
    def change_empty_return_end_location_in_CFO(self):
        for row in self.grounded_filled_containers:
            if row.reference_container:
                container_number = frappe.get_value("FPL Containers", {"name": row.reference_container}, "container_number")
                CFO = frappe.get_doc("FPL Freight Orders", self.freight_for_container(row.reference_container))
                
                # Fetch the specific Empty Return job
                EmptyReturn =  frappe.get_list("FPLRoadJob", 
                    filters={
                        "container_number": container_number,
                        "freight_order_id": CFO.name,
                        "sales_order_number": self.booking_order_id,
                        "job_type": ["in", service_names("Empty Return")]
                    }, 
                    fields=["name"]
                )
                if EmptyReturn:
                    EmptyReturn = frappe.get_doc("FPLRoadJob", EmptyReturn[0].name)
                else:
                    continue  # Export profiles need not contain an Empty Return.
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
        requests = set()
        for container in sorted({row.reference_container for row in self.grounded_filled_containers}):
            freight = frappe.get_doc('FPL Freight Orders', self.freight_for_container(container), for_update=True)
            if freight.cargo_request:
                requests.add(freight.cargo_request)
                freight.db_set('cargo_cross_stuff_performance', self.name, update_modified=False)
        for name in sorted(requests):
            request = frappe.get_doc('Container or Vehicle Request', name, for_update=True)
            if request.booking_order_id != self.booking_order_id or request.docstatus != 1:
                frappe.throw('Receiving Freight Order has an invalid container request lineage.')
            remaining = frappe.db.sql('''SELECT name FROM `tabFPL Freight Orders`
                WHERE cargo_request=%s AND COALESCE(cargo_cross_stuff_performance,'')='' FOR UPDATE''', name)
            if not remaining:
                request.db_set('cross_stuff_performance', self.name, update_modified=False)
        # Historical receivers without a request link are deliberately not
        # assigned by quantity; equal counts cannot prove document ownership.
