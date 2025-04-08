# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FPLWagoncdt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		loaded_: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		status: DF.Data | None
		wagon_number: DF.Link | None
		wagon_type: DF.Link | None
	# end: auto-generated types
	pass
