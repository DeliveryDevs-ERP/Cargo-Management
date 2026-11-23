from cargo_management.setup import get_account_manager_emails
# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _
from cargo_management.cargo_management.utils.Update_JOB_Container_FO_Status import updateJobStatus
from cargo_management.cargo_management.utils.getJobTypebyID import get_job_type_by_id
from cargo_management.cargo_management.utils.getSupplierForCostType import get_supplier
from cargo_management.cargo_management.utils.api import create_invoice
from frappe.utils import getdate, get_link_to_form

class MiddleMileWeightError(frappe.ValidationError):
	pass

class FPLPerformMiddleMile(Document):
    def _set_defaults(self):
        # Frappe otherwise injects a global Company default before validation.
        # Preserve explicit ownership and resolve absent NEW ownership only
        # from the user's actual selectable Company scope.
        supplied_company = self.get('company')
        super()._set_defaults()
        self.company = supplied_company
        if self.is_new() and not self.company:
            from cargo_management.cargo_management.utils.configuration import get_train_company_context
            self.company = get_train_company_context()['sole_company']

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
        from cargo_management.cargo_management.utils.rail_allocations import validate_allocations
        validate_allocations(self)
        
        if self.finish_train_formation == 1 and self.finish_loading == 0: # formation is completed now completing loading
            self.fill_child_middle_mile_tables_with_WagonName_rows()
        
        if self.finish_train_formation == 1 and self.finish_loading == 1 and self.finish_departure == 0: # formation & loading is completed now completing departure
            self.carry_forward_the_specified_rows()
            
        if self.finish_train_formation == 1 and self.finish_loading == 1 and self.finish_departure == 1 and self.finish_arrival==0: # formation, loading & departure is completed now completing arrival
            self.carry_forward_the_specified_row2()
            self.update_gate_out_jobs() # do gate out job
            
        old = self.get_doc_before_save()
        legacy_arrival = old and old.finish_arrival and old.expenses and not any(row.get('cargo_charge_key') for row in old.expenses)
        if self.finish_train_formation == 1 and self.finish_loading == 1 and self.finish_departure == 1 and self.finish_arrival==1 and not legacy_arrival:
            self.arrival_update_wagon()
            self.bulk_update_container_status()
            self.calculate_expenses()
            self.create_purchase_invoice()
        
        if len(self.expenses) > 0:
            self.send_expense_invoice_notification()
            
    def on_trash(self):
        current=frappe.get_doc(self.doctype,self.name,for_update=True)
        if current.status not in (None,'','Train Formed') or current.finish_loading or current.finish_departure or current.finish_arrival or current.expenses:
            frappe.throw(_('Loaded, departed, received or cost-bearing trains cannot be deleted.'))
        wagons=[]
        for row in sorted(current.wagons,key=lambda value:value.wagon_number):
            wagon=frappe.get_doc('Wagons',row.wagon_number,for_update=True)
            if wagon.train_no and wagon.train_no!=current.name:
                frappe.throw(_('This wagon belongs to another train; its allocation will not be cleared.'))
            wagons.append(wagon)
        for wagon in wagons:
            frappe.db.set_value('Wagons',wagon.name,'train_no','')

    def fill_child_middle_mile_tables_with_WagonName_rows(self): # Loading of Containers
        if self.loading_time is None and self.loading_end_time is None: #this will only happen if loading times are not given
            for wagon in self.get('wagons'):
                if wagon.loaded_ == 0: #only create rows for the wagon that is not already loaded
                    wagon_doc = frappe.get_doc('FPL Wagons', wagon.wagon_type)
                    max_count = wagon_doc.max_count if wagon_doc else 0
                    existing = sum(row.wagon_number == wagon.wagon_number for row in self.middle_mile)
                    for _ in range(max(0, max_count - existing)):
                        self.append('middle_mile', {
                            'wagon_number': wagon.wagon_number,
                            'job': 'Middle Mile',
                            'mm_job_id': None,  
                            'container': None,  
                            'read_only': False  
                        })
                frappe.db.set_value("Wagons", wagon.wagon_number, "train_no", self.name)

    def carry_forward_the_specified_rows(self): # loading completed of containers
        middle_mile_rows = self.get('middle_mile')
        filtered_rows2 = [row for row in middle_mile_rows if row.wagon_number and not row.container]
        seen_wagons = set()
        filtered_rows = [row for row in middle_mile_rows if row.container and row.wagon_number]
        loaded_wagon_numbers = {row.wagon_number for row in filtered_rows}
        self.middle_mile_in_loading = []
        for row in filtered_rows:
            self.append('middle_mile_in_loading', {
                'wagon_number': row.wagon_number,
                'job': row.job,
                'mm_job_id': row.mm_job_id,
                # 'received_': row.received_,
                'loaded_':1,
                'container': row.container,
                'size': row.size,
                'weight': row.weight,
                'read_only': True  
            })
            frappe.db.set_value("Wagons", row.wagon_number, "loaded_", "1")
            frappe.db.set_value("Wagons", row.wagon_number, "train_no", self.name)
            frappe.db.set_value("Wagons", row.wagon_number, "status", "Loaded")
            for row2 in self.get('wagons'):
                if row2.wagon_number == row.wagon_number:
                    row2.loaded_ = 1
            for row in filtered_rows2:
                if row.wagon_number not in seen_wagons and row.wagon_number not in loaded_wagon_numbers:
                    seen_wagons.add(row.wagon_number)
                    self.append('middle_mile_in_loading', {
                        'wagon_number': row.wagon_number,
                        'job': "",
                        'mm_job_id': "",
                        'loaded_':0,
                        'container': "",
                        'size': row.size,
                        'weight': row.weight,
                        'read_only': True  
                    })
                    frappe.db.set_value("Wagons", row.wagon_number, "loaded_", "0")
                    frappe.db.set_value("Wagons", row.wagon_number, "train_no", self.name)
                    frappe.db.set_value("Wagons", row.wagon_number, "status", "Loaded")
                    for row2 in self.get('wagons'):
                        if row2.wagon_number == row.wagon_number:
                            row2.loaded_ = 0
            

    def carry_forward_the_specified_row2(self):
        middle_mile_rows = self.get('middle_mile_in_loading')
        filtered_rows = [row for row in middle_mile_rows if (row.departed_ == 1)]
        derailed_rows = [row for row in middle_mile_rows if (row.departed_ == 0)]
        self.middle_mile_copy = []
        for row in filtered_rows:
            self.append('middle_mile_copy', {
                'wagon_number': row.wagon_number,
                'job': row.job,
                'mm_job_id': row.mm_job_id,
                'container': row.container,
                'read_only': False  
            })
            # doc = frappe.get_doc("Wagons", row.wagon_number)
            frappe.db.set_value("Wagons", row.wagon_number, "status", "In Transit")
        for wagon in self.get('wagons'):
            frappe.db.set_value("Wagons", wagon.wagon_number, "status", "In Transit")
        for row in derailed_rows:
            frappe.db.set_value("Wagons", row.wagon_number, "status", "Derailed")
                
    def bulk_update_container_status(self):
        for row in self.middle_mile_copy:
            if row.container and row.received_:
                # Retrieve Freight Order and Job IDs based on container number
                container_number = frappe.db.get_value("FPL Containers", {"name": row.container}, "container_number")
                freight_order_id = frappe.db.get_value("FPL Containers", {"name": row.container}, "freight_order_id")
                mm_job_id = frappe.db.get_value("FPLRailJob", {"container_number": container_number, "freight_order_id": freight_order_id}, "name")

                #frappe.msgprint(f"Processing container: {container_number}")
                #frappe.msgprint(f"Freight Order ID: {freight_order_id}, Middle Mile Job ID: {mm_job_id}")

                if freight_order_id and mm_job_id:
                    if frappe.db.get_value('FPL Freight Orders',freight_order_id,'mm_completed_'):
                        continue  # Arrival already applied; do not append duplicate gate jobs.
                    # Update job status as needed
                    frappe.db.set_value("FPLRailJob",mm_job_id,"train_number",self.name)
                    frappe.db.set_value("FPLRailJob",mm_job_id,"train_arrival_datetime",self.actual_arrival_datetime)
                    if not updateJobStatus(mm_job_id, freight_order_id, container_number):
                        frappe.throw(_('Middle Mile arrival cannot bypass unfinished preceding jobs.'))
                    rail_job_doc = frappe.get_doc("FPLRailJob", mm_job_id)
                    rail_job_doc.flags.cargo_receipt_verified = True
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
                        from cargo_management.cargo_management.utils.configuration import resolve_service, freight_company
                        company = freight_company(freight_order)
                        gate_in_type_name = resolve_service('Gate In', company=company)
                        gate_out_type_name = resolve_service('Gate Out', company=company)

                        # Prepare the "Gate In" job document with an initial status of "Draft"
                        gate_in_job = frappe.get_doc({
                            'doctype': 'FPLYardJob',
                            'freight_order_id': freight_order_id,
                            #'name': "Gate In-" + str(int(frappe.get_last_doc('FPLYardJob').name.split('-')[-1]) + 1),
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
                            #'name': "Gate Out-" + str(int(frappe.get_last_doc('FPLYardJob').name.split('-')[-1]) + 1),
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

    def arrival_update_wagon(self):
        groups={}
        for row in self.middle_mile_copy:
            if row.container:groups.setdefault(row.wagon_number,[]).append(bool(row.received_))
        for wagon, received in groups.items():
            status='Received' if all(received) else 'Derailed' if not any(received) else 'In Transit'
            frappe.db.set_value('Wagons',wagon,{'status':status,'loaded_':int(status!='Received')})
        for row2 in self.get('wagons'):
            if row2.wagon_number:
                frappe.db.set_value("Wagons", row2.wagon_number, "status", "Received")
                
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
                freight_order_id = frappe.db.get_value("FPL Containers", {"name": row.container}, "freight_order_id")
                # Get the Freight Order ID associated with the container
                # freight_order_id = frappe.db.get_value("FPL Freight Orders", {"container_number": container_number}, "name")

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

                            except Exception:
                                raise  # Native request rollback must include the complete departure.

                        
    def validate_expected_dates(self):
        if self.expected_departure_time_eda and self.expected_time_of_arrival_eta:
            if self.expected_time_of_arrival_eta < self.expected_departure_time_eda:
                frappe.throw(_("The expected time of arrival (ETA) cannot be before the expected departure time (EDA)."))

    def send_expense_invoice_notification(self):
        pending_expenses = []
        for expense in self.expenses:
            if expense.invoiced_ == 1 and not expense.sales_invoice_no:
                pending_expenses.append(expense)
    
        if not pending_expenses:
            return
        bookings={frappe.db.get_value('FPL Containers',expense.container_number,'booking_order_id') for expense in pending_expenses}
        if None in bookings:
            frappe.throw(_('A train expense notification requires verified Booking references.'))
        recipient_sets=[set(get_account_manager_emails(booking)) for booking in bookings]
        recipient_emails=sorted(set.intersection(*recipient_sets)) if recipient_sets else []
        if not recipient_emails:
            return
        
        job_link = get_link_to_form("FPL Perform Middle Mile", self.name)

        rows = ""
        for expense in pending_expenses:
            booking_order = frappe.db.get_value("FPL Containers", expense.container_number, "booking_order_id")
            cNumber = frappe.db.get_value("FPL Containers", expense.container_number, "container_number")
            sales_order = frappe.db.get_value("Sales Order", {"custom_booking_order_id": booking_order}, "name")
            rows += f"""
            <tr>
                <td>{expense.expense_type}</td>
                <td>{expense.amount}</td>
                <td>{cNumber}</td>
                <td>{booking_order}</td>
                <td>{sales_order}</td>
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
                                <li><b>Job Document:</b> {job_link}</li>
                            </ul>
                            <br>
                            <table border="1" cellpadding="5" cellspacing="0" style="width:100%; border-collapse: collapse;">
                                <thead style="background: #f0f0f0;">
                                    <tr>
                                        <th>Expense Type</th>
                                        <th>Amount</th>
                                        <th>Container Number</th>
                                        <th>Booking ID</th>
                                        <th>Sales Order</th>
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

    def calculate_expenses(self):
        from cargo_management.cargo_management.utils.rail_charges import append_train_charges
        return append_train_charges(self)


    def create_purchase_invoice(self):
        from cargo_management.cargo_management.utils.configuration import train_company
        default_company = train_company(self)
        for expense in self.expenses:
            if not expense.purchase_invoiced_created:
                item = frappe.get_value("FPL Cost Type", expense.expense_type, 'item_id')
                FO = frappe.get_value("FPL Containers", expense.container_number, 'freight_order_id')
                BO = frappe.get_value("FPL Freight Orders",FO,'sales_order_number')
                if item:
                    code = create_invoice(
                        container_number=expense.container_number,
                        train_no=self.rail_number,
                        movement_type=self.movement_type,
                        PM = self.name,
                        FO=FO,
                        BO=BO,
                        crm_bill_no=expense.name,
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
                            
@frappe.whitelist()
def cancel_departure(docname):
    from cargo_management.cargo_management.utils.rail_reversal import rewind
    return rewind(docname, 'departure')


@frappe.whitelist()
def validate_weight_Loading(docname):
    doc = frappe.get_doc('FPL Perform Middle Mile', docname)
    doc.check_permission('read')
    
    wagon_groups = {}
    for row in doc.get('middle_mile'):
        if row.container:
            if row.wagon_number not in wagon_groups:
                wagon_groups[row.wagon_number] = []
            wagon_groups[row.wagon_number].append(row)

    for wagon_number, rows in wagon_groups.items():
        wagon_type = None
        for wagon in doc.get('wagons'):
            if wagon.wagon_number == wagon_number:
                wagon_type = wagon.wagon_type
                break

        if not wagon_type:
            return False

        wagon_doc = frappe.get_doc('FPL Wagons', wagon_type)
        max_weight_ton = wagon_doc.max_weight_ton if wagon_doc else 0
        total_weight = sum(float(row.weight or 0) for row in rows)
        # frappe.errprint(f"Total Weight {total_weight} Max Weight {max_weight_ton}")
        if total_weight > max_weight_ton:
            # frappe.throw(_(f"Total weight of containers in wagon {wagon_number} exceeds the maximum allowed weight of {max_weight_ton} tons. Current total weight: {total_weight} tons"))
            return False

    return True


@frappe.whitelist()
def cancel_loading(docname):
    from cargo_management.cargo_management.utils.rail_reversal import rewind
    return rewind(docname, 'loading')
