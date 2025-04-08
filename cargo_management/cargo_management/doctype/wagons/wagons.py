# Copyright (c) 2025, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Wagons(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		loaded_: DF.Check
		status: DF.Literal["", "Loaded", "In Transit", "Received", "Derailed"]
		train_no: DF.Link | None
		type: DF.Link
		wagon_number: DF.Data
	# end: auto-generated types
	pass
