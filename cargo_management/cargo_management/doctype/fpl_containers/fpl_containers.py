# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FPLContainers(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active_job_id: DF.Data | None
		booking_order_id: DF.Data | None
		container_location: DF.Link | None
		container_next_location: DF.Link | None
		container_number: DF.Data | None
		container_type: DF.Link | None
		freight_order_id: DF.Data | None
		state: DF.Literal["", "Loaded", "In transit", "Gate In", "Gate Out", "Delivered"]
		status: DF.Literal["", "Empty", "Filled"]
	# end: auto-generated types
	pass
