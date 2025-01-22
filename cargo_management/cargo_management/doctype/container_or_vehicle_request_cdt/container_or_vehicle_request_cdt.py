# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ContainerorVehicleRequestcdt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		empty_return_location: DF.Link | None
		last_free_date: DF.Datetime | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		pickup_location: DF.Link | None
		qty: DF.Int
		size: DF.Literal["", "20", "40", "45"]
		type: DF.Link | None
	# end: auto-generated types
	pass
