# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FPLCommodities(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		comodity_name: DF.Literal["", "Bulk Goods", "Manufactured", "Consumer Goods", "Non Perishable Food", "Industrial"]
	# end: auto-generated types
	pass
