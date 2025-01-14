# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CargoDetailcdt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		avg_weight: DF.Float
		bag_qty: DF.Int
		bag_weight: DF.Float
		cargo_type: DF.Link
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		qty: DF.Int
		rate: DF.Float
		rate_type: DF.Link
		size: DF.Literal["", "20", "40"]
	# end: auto-generated types
	pass
