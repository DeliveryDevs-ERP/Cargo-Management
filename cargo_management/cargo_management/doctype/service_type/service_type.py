# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ServiceType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		applicable: DF.Check
		job_type: DF.Literal["", "Road", "Rail", "Yard", "Cross Stuff"]
		miscellaneous: DF.Check
		name1: DF.Data | None
		transport_mode: DF.Link | None
	# end: auto-generated types
	pass
