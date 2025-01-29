# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class GroundedFilledCdt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		bags_to_transfer: DF.Int
		container_number: DF.Link | None
		empty_return_location: DF.Link | None
		fo_bags_qty: DF.Int
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		reference_container: DF.Link | None
		weight: DF.Float
		weight_to_transfer: DF.Float
	# end: auto-generated types
	pass
