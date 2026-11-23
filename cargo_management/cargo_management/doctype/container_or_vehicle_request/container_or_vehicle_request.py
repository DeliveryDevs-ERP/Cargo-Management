# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe.utils import getdate, random_string

from cargo_management.cargo_management.utils.getJobTypebyID import get_job_type_by_id


class ContainerorVehicleRequest(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from cargo_management.cargo_management.doctype.container_or_vehicle_request_cdt.container_or_vehicle_request_cdt import ContainerorVehicleRequestcdt
        from frappe.types import DF

        amended_from: DF.Link | None
        booking_order_id: DF.Link | None
        cargo_type: DF.Literal["", "Containerised", "Non Containerised"]
        cross_stuff_performance: DF.Link | None
        request_date: DF.Datetime | None
        table_ktch: DF.Table[ContainerorVehicleRequestcdt]
        yard_location: DF.Link
    # end: auto-generated types

    def validate(self):
        # A receiving allocation is a whole physical container, not an empty
        # range silently produced by zero/negative quantities.
        from frappe.utils import flt
        for row in self.get('table_ktch') or []:
            quantity = flt(row.qty)
            if quantity <= 0 or quantity != int(quantity):
                frappe.throw('Receiving request quantities must be positive whole allocations.')
            if row.type and str(frappe.db.get_value('Container Type', row.type, 'size')) != str(row.size):
                frappe.throw('Receiving request size must match its selected Container Type.')

    def before_cancel(self):
        # Native cancellation checks submitted links; receiving Freight Orders
        # are non-submittable. Keep their provenance rather than leaving live
        # work linked to a cancelled request or deleting it implicitly.
        if self.cross_stuff_performance or frappe.db.exists('FPL Freight Orders', {'cargo_request': self.name}):
            frappe.throw('Receiving work exists. Reverse or resolve the linked work before cancelling this request; no operational or financial history is deleted automatically.')

    def on_submit(self):
        try:
            self.create_CrossStuffFreight_orders()  # Create freight orders first
            # self.create_and_submit_sales_order()  # Attempt to create and submit Sales Order
        except Exception as e:
            frappe.throw(f"Booking Order submission failed due to: {str(e)}")

    def create_CrossStuffFreight_orders(self):
        Request = self.get('table_ktch')

        for item in Request:
            for _ in range(int(item.qty)):
                self.create_CFO(item)

    def create_CFO(self, item):
        size = item.size if item.size else None
        freight_order = frappe.get_doc({
            'doctype': 'FPL Freight Orders',
            'freight_order_number':  self.get_next_name("CFO-"),
            'sales_order_number': self.booking_order_id,
            'cargo_request': self.name,
            'client': self.get_Client_from_BO(),
            'weight': None,
            'size': size,
            'jobs': []
        })

        # Determine transport type based on cargo type
        transport_type = "Rail (Train)" if self.cargo_type == "Containerised" else "Road (Truck)"

        # Add jobs to the freight order
        freight_order.append('jobs', {
            'job_name': self.get_service_type_name('Empty Pickup', transport_type),
            'status': 'Draft',
            'start_location': item.pickup_location,
            'end_location': self.yard_location
        })
        freight_order.append('jobs', {
            'job_name': self.get_service_type_name('Gate In', transport_type),
            'status': 'Draft',
            'start_location': self.yard_location,
            'end_location': self.yard_location
        })
        freight_order.append('jobs', {
            'job_name': self.get_service_type_name('Gate Out', transport_type),
            'status': 'Draft',
            'start_location': self.yard_location,
            'end_location': self.yard_location
        })

        freight_order.insert()

        if freight_order.jobs:
            freight_order.next_job = get_job_type_by_id(freight_order.jobs[0].job_id)
            freight_order.save()


    def get_service_type_name(self, service_name, transport_mode):
        from cargo_management.cargo_management.utils.configuration import resolve_service, booking_company
        return resolve_service(service_name, transport_mode, booking_company(self.booking_order_id))

    def get_Client_from_BO(self):
        """
        Fetches the client from the Booking Order associated with the current document's booking_order_id.
        """
        # Fetch the Booking Order document using the booking_order_id
        booking_order = frappe.get_doc("Booking Order", self.booking_order_id)
        # Return the client field from the Booking Order
        return booking_order.customer

    def get_next_name(self, key):
        from cargo_management.cargo_management.utils.naming import freight_name
        return freight_name(key, self.booking_order_id)
