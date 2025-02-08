# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Expensescdt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Float
		client: DF.Link | None
		container_number: DF.Link | None
		expense_type: DF.Link | None
		invoiced_: DF.Check
		job_id: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		purchase_invoice_no: DF.Data | None
		purchase_invoiced_created: DF.Check
		remarks: DF.SmallText | None
		sales_invoice_no: DF.Link | None
		slip: DF.AttachImage | None
	# end: auto-generated types
	pass
