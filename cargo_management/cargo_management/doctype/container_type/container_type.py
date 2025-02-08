# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ContainerType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		capacity_m3: DF.Int
		height_m: DF.Float
		length_m: DF.Float
		max_cargo_weight_kg: DF.Int
		name1: DF.Data | None
		name: DF.Int | None
		size: DF.Int
		tare_weight_kg: DF.Int
		width_m: DF.Float
	# end: auto-generated types
	pass
