# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FPLCostType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cost: DF.Float
		cost_name: DF.Data
		fixed_: DF.Check
		item_id: DF.Link | None
		job_mode: DF.Literal["", "Train Job", "Truck Job", "Yard Job", "Cross Stuff Job"]
	# end: auto-generated types
	pass
