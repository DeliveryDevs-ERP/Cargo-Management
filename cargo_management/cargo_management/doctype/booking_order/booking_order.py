from frappe.model.document import Document
import frappe
from frappe.utils import getdate, random_string

from cargo_management.cargo_management.utils.getJobTypebyID import get_job_type_by_id


class BookingOrder(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from cargo_management.cargo_management.doctype.cargo_detail_cdt.cargo_detail_cdt import CargoDetailcdt
        from cargo_management.cargo_management.doctype.fpl_servicess.fpl_servicess import FPLServicess
        from frappe.types import DF

        amended_from: DF.Link | None
        bill_of_landing_number: DF.Data | None
        bill_to: DF.Literal[None]
        cargo_details: DF.Table[CargoDetailcdt]
        cargo_owner: DF.Link | None
        commodity: DF.Link | None
        company: DF.Link | None
        customer: DF.Link
        delivery_date: DF.Date
        demurrage_date: DF.Date | None
        dropoff_location: DF.Link | None
        empty_pickup_dropoff_location: DF.Link | None
        empty_pickup_location: DF.Link | None
        empty_return_dropoff_location: DF.Link | None
        empty_return_pickup_location: DF.Link | None
        fm_dropoff_location: DF.Link | None
        fm_pickup_location: DF.Link | None
        lm_dropoff_location: DF.Link | None
        lm_pickup_location: DF.Link | None
        location_of_cross_stuff: DF.Link | None
        long_haul_dropoff_location: DF.Link | None
        long_haul_pickup_location: DF.Link | None
        miscellaneous_services: DF.Table[FPLServicess]
        mm_loading_station: DF.Link | None
        mm_offloading_station: DF.Link | None
        naming_series: DF.Literal["BO-.YYYY.-"]
        pickup_location: DF.Link | None
        sales_order_date: DF.Date
        sales_order_type: DF.Literal["", "Import", "Export", "Domestic"]
        sales_person: DF.Link | None
        services: DF.Table[FPLServicess]
        shipping_line: DF.Link | None
        short_haul_dropoff_location: DF.Link | None
        short_haul_pickup_location: DF.Link | None
        total: DF.Currency
        transport_type: DF.Link
    # end: auto-generated types
    def validate(self):
        self.validate_demurrage_date()

    def validate_demurrage_date(self):
        if self.demurrage_date and self.delivery_date:
            demurrage_date = getdate(self.demurrage_date)
            delivery_date = getdate(self.delivery_date)
            if demurrage_date <= delivery_date:
                frappe.throw("Demurrage date must be after the delivery date.")

    def on_submit(self):
        try:
            self.create_freight_orders() 
            self.create_and_submit_sales_order()
        except Exception as e:
            frappe.db.rollback()  # Roll back changes if any error occurs
            frappe.throw(f"Booking Order submission failed due to: {str(e)}")

    def create_freight_orders(self):
        cargo_details = self.get('cargo_details')  
        services = self.get('services')

        for item in cargo_details:
            for _ in range(int(item.qty)):  
                self.create_freight_order(item, services)

    def create_freight_order(self, item, services):
        applicable_services = [service for service in services if service.applicable == 1]
        # crossStuff_flag = any(service.service_name == "Cross Stuff" for service in applicable_services) # check if there is cross stuff present
        # if crossStuff_flag:
            # applicable_services = [service for service in applicable_services if service.service_name != "Cross Stuff"]
        weight = item.avg_weight if item.avg_weight else item.bag_weight
        size = item.size if item.size else None
        freight_order = frappe.get_doc({
            'doctype': 'FPL Freight Orders',
            'freight_order_number': self.get_next_name("FO-"),
            'sales_order_number': self.name,
            'client': self.customer,
            'weight': weight, 
            'size':size,
            'jobs': [] 
        })

        ordered_services = self.get_ordered_services(applicable_services)

        for service in ordered_services:
            if service.service_name == 'Middle Mile':
                freight_order.append('jobs', {
                'job_name': self.get_service_type_name('Gate In', self.transport_type), 
                'status': 'Draft',
                'start_location': self.get_Job_LocationPickup(service.service_name),
                'end_location':self.get_Job_LocationPickup(service.service_name)
                })
                freight_order.append('jobs', {
                'job_name': self.get_service_type_name('Gate Out', self.transport_type), 
                'status': 'Draft',
                'start_location': self.get_Job_LocationPickup(service.service_name),
                'end_location': self.get_Job_LocationPickup(service.service_name)
                })
                freight_order.append('jobs', {
                'job_name': self.get_service_type_name(service.service_name, self.transport_type),
                'status': 'Draft',
                'start_location': self.get_Job_LocationPickup(service.service_name),
                'end_location': self.get_Job_LocationDropoff(service.service_name)
                })
                
            else:
                freight_order.append('jobs', {
                'job_name': self.get_service_type_name(service.service_name, self.transport_type),
                'status': 'Draft',
                'start_location': self.get_Job_LocationPickup(service.service_name),
                'end_location': self.get_Job_LocationDropoff(service.service_name)
                })
        

        

        # Cross Stuff adjustment in the jobs order:
        # if crossStuff_flag:
        #     cross_stuff_index = next((index for index, job in enumerate(freight_order.jobs) if job.job_name == self.location_of_cross_stuff), None)
        #     freight_order.append('jobs', {
        #         'job_name': self.get_service_type_name("Cross Stuff", self.transport_type),
        #         'status': 'Draft',
        #         'start_location': freight_order.jobs[cross_stuff_index - 1].end_location if cross_stuff_index > 0 else freight_order.jobs[0].start_location,
        #         'end_location': None
        #     })

        freight_order.insert()
        if freight_order.jobs:
            freight_order.next_job = get_job_type_by_id(freight_order.jobs[0].job_id) 
            freight_order.save()

            
        frappe.db.commit()

        # if crossStuff_flag:
        #     self.reorder_Freight_orderJobs_after_crossStuff_insert(freight_order,cross_stuff_index)

            
    def get_next_name(self, key):
        try:
            # Try to get the last document in the series
            current = frappe.get_last_doc('FPL Freight Orders')
            if current:
                name_parts = current.name.split('-')
                if name_parts:
                    # Assuming the last part is the numeric
                    next_number = int(name_parts[-1]) + 1
                    new_name = f"{key}{next_number:04d}"  # Pad with zeros if needed
                    return new_name
        except frappe.DoesNotExistError:
            # If no documents are found, start at the beginning of the series
            return f"{key}0001"

        # Fallback in case of any other unexpected issue
        return f"{key}0001"


    def get_Job_LocationPickup(self, serviceName):
        if serviceName == 'First Mile':
            return self.fm_pickup_location
        elif serviceName == 'Middle Mile':
            return self.mm_loading_station
        elif serviceName == 'Last Mile':
            return self.lm_pickup_location
        elif serviceName == 'Empty Pickup':
            return self.empty_pickup_location
        elif serviceName == 'Empty Return':
            return self.empty_return_pickup_location
        elif serviceName == 'Cross Stuff':
            return self.location_of_cross_stuff
        elif serviceName == 'Long Haul':
            return self.long_haul_pickup_location
        elif serviceName == 'Short Haul':
            return self.short_haul_pickup_location
        else:
            return None

    def get_Job_LocationDropoff(self, serviceName):
        if serviceName == 'First Mile':
            return self.fm_dropoff_location
        elif serviceName == 'Middle Mile':
            return self.mm_offloading_station
        elif serviceName == 'Last Mile':
            return self.lm_dropoff_location
        elif serviceName == 'Empty Pickup':
            return self.empty_pickup_dropoff_location
        elif serviceName == 'Empty Return':
            return self.empty_return_dropoff_location
        elif serviceName == 'Cross Stuff':
            return None  
        elif serviceName == 'Long Haul':
            return self.long_haul_dropoff_location
        elif serviceName == 'Short Haul':
            return self.short_haul_dropoff_location
        else:
            return None


    def get_ordered_services(self, services):
        if not services:
            return []        
        job_sequence = frappe.get_all('FPL Jobs Sequence', 
                                        fields=['service_name', 'sequence'], 
                                        filters={'transport_mode': self.transport_type,
                                                'sales_order_type': self.sales_order_type},
                                        order_by='sequence asc')
        service_map = {service.services: service for service in services if service.applicable == 1}  
        ordered_services = []
        for seq in job_sequence:
            service_name = seq['service_name']  
            matching_service = next((s for s in services if s.services == service_name), None)
            if matching_service:
                ordered_services.append(matching_service)  
        return ordered_services

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

    def create_and_submit_sales_order(self):
        try:
            # Create Sales Order
            sales_order = frappe.get_doc({
                "doctype": "Sales Order",
                "customer": self.bill_to,
                "company": self.company,  
                "items": self.get_sales_order_items(),
                "status": "To Deliver and Bill",
                "order_type": "Sales",
                "transaction_date": self.sales_order_date,
                "custom_booking_order_id" : self.name,
                "delivery_date": self.delivery_date, 
            })

            # Save and save the Sales Order
            sales_order.insert()
            sales_order.save()

            # frappe.msgprint(f"Sales Order {sales_order.name} created and save successfully.")
            return sales_order.name  # Return Sales Order name if needed

        except Exception as e:
            # Raise an error if the Sales Order submission fails
            frappe.throw(f"Failed to create and save Sales Order: {str(e)}")


    def get_sales_order_items(self):
        """Extract items from the Booking Order to populate Sales Order."""
        sales_order_items = []
        for cargo in self.get("cargo_details", []):
            UOM = cargo.rate_type
            if (UOM == "Per Container"):
                weight = cargo.avg_weight
                qty = cargo.qty
            elif (UOM == "Per Weight(Ton)")or (UOM == 'Per Bag'):
                weight = cargo.bag_weight
                qty = cargo.bag_qty
            sales_order_items.append({
                "item_code": cargo.cargo_type,
                "qty": qty,  
                "uom": cargo.rate_type,
                "rate": cargo.rate, 
                "amount" : cargo.amount,
                "weight_per_unit": weight,
                "description": f"Transport Mode: {self.transport_type}, Container Size: {cargo.size}, Avg Weight: {cargo.avg_weight or cargo.bag_weight} Tons, from {self.pickup_location} to {self.dropoff_location}, BOL: {self.bill_of_landing_number}"
            })
        return sales_order_items

    def create_and_submit_sales_invoice(self):
        try:
            # Create Sales Invoice
            sales_invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": self.bill_to,  # Assuming 'bill to' is available in Booking Order
                "company": self.company,  
                "items": self.get_sales_invoice_items(),
                "status": "Draft",
                "posting_date": frappe.utils.nowdate(),  # Use current date as posting date
                "due_date": frappe.utils.add_days(frappe.utils.nowdate(), 30),  # Example: 30 days from posting date
                "custom_booking_order": self.name,  # Link to the Booking Order for reference
            })

            # Save and submit the Sales Invoice
            sales_invoice.insert()
            sales_invoice.save()

            # frappe.msgprint(f"Sales Invoice {sales_invoice.name} created and saved successfully.")
            return sales_invoice.name  # Return Sales Invoice name if needed

        except Exception as e:
            # Raise an error if the Sales Invoice submission fails
            frappe.throw(f"Failed to create and submit Sales Invoice: {str(e)}")


    def get_sales_invoice_items(self):
        """Extract items from the Booking Order to populate Sales Invoice."""
        sales_invoice_items = []
        for cargo in self.get("cargo_details", []):
            UOM = cargo.rate_type
            if UOM == "Per Container":
                weight = cargo.avg_weight
                qty = cargo.qty
            elif UOM in ("Per Weight(Ton)", "Per Bag"):
                weight = cargo.bag_weight
                qty = cargo.bag_qty
            sales_invoice_items.append({
                "item_code": cargo.cargo_type,  # Assuming cargo contains 'item_code'
                "qty": qty,  
                "uom": cargo.rate_type,
                "rate": cargo.rate, 
                "amount": cargo.amount,
                "weight_per_unit": weight,
                "description": f"Transport Mode: {self.transport_type}, Container Size: {cargo.size}, Avg Weight: {cargo.avg_weight or cargo.bag_weight} Tons, from {self.pickup_location} to {self.dropoff_location}, BOL: {self.bill_of_landing_number}"
            })
        return sales_invoice_items

    
    def reorder_Freight_orderJobs_after_crossStuff_insert(self, freight_order, initial_cross_stuff_index):
        # Log the initial index for troubleshooting
        frappe.errprint(f"Initial cross_stuff_index: {initial_cross_stuff_index}")
        
        # Verify that the initial_cross_stuff_index is valid and within bounds
        if initial_cross_stuff_index is None or initial_cross_stuff_index >= len(freight_order.jobs):
            frappe.throw("Invalid index for Cross Stuff job.")

        # Remove the "Cross Stuff" job from its initial position
        cross_stuff_job = freight_order.jobs.pop(initial_cross_stuff_index)

        # Determine the new position for the "Cross Stuff" job
        # Example: 2 positions after its initial index or adjust based on your specific requirements
        new_position = initial_cross_stuff_index + 2
        
        # Ensure new position does not exceed the list size
        if new_position > len(freight_order.jobs):
            new_position = len(freight_order.jobs)

        # Insert the "Cross Stuff" job at the new position
        freight_order.jobs.insert(new_position, cross_stuff_job)
        
        # Log the adjusted positions for troubleshooting
        frappe.errprint(f"New position for Cross Stuff job: {new_position}")

        # Update the indices for all jobs to maintain consistency
        for idx, job in enumerate(freight_order.jobs):
            job.idx = idx + 1  # Update the index for each job to reflect its new position in the list
        
        # Save changes to the Freight Order
        freight_order.save()
        frappe.db.commit()
            
    
@frappe.whitelist()
def get_sales_person(customer):
    """
    Fetch the first Sales Person associated with the given customer from the Sales Team doctype.
    """
    # Ensure the method only fetches data if there's a valid customer ID
    if not customer:
        return None

    # Attempt to fetch the first sales person from the Sales Team linked to the customer
    sales_person = frappe.get_value("Sales Team", 
                                    filters={
                                        "parenttype": "Customer",
                                        "parent": customer,
                                        "sales_person": ["!=", ""]
                                    },
                                    fieldname="sales_person",
                                    order_by="idx asc")


    # Return the fetched sales person or None if not found
    return sales_person