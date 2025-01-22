# Copyright (c) 2025, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RailFreightCost(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		avg_weight: DF.Float
		avg_weight_40: DF.Float
		container_count: DF.Int
		container_count_40: DF.Int
		rate_20: DF.Currency
		rate_40: DF.Currency
		wagon_type: DF.Literal["", "Small", "Conventional", "Large", "Dummy", "Break"]
	# end: auto-generated types
	pass
