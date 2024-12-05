# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FPLMMcdt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		container: DF.Link | None
		container_number: DF.Data | None
		job: DF.Data | None
		mm_job_id: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		received_: DF.Check
		wagon_number: DF.Data | None
	# end: auto-generated types
	pass
