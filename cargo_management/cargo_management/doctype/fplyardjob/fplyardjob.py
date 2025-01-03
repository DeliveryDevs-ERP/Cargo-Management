# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt
from cargo_management.cargo_management.utils.Update_JOB_Container_FO_Status import updateJobStatus
from frappe.utils import now_datetime
import frappe
from frappe.model.document import Document


class FPLYardJob(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from cargo_management.cargo_management.doctype.expenses_cdt.expenses_cdt import Expensescdt
		from frappe.types import DF

		assigned_at: DF.Datetime | None
		client: DF.Link | None
		container_number: DF.Data | None
		expenses: DF.Table[Expensescdt]
		freight_order_id: DF.Data | None
		gate_in: DF.Datetime | None
		gate_out: DF.Datetime | None
		job_end_location: DF.Link | None
		job_start_location: DF.Link | None
		job_type: DF.Link | None
		sales_order_number: DF.Data | None
		status: DF.Literal["", "Draft", "Assigned", "Completed", "Cancelled"]
	# end: auto-generated types

	def validate(self):
		if (self.gate_in or self.gate_out) and self.status != "Completed":
			if updateJobStatus(self.name , self.freight_order_id, self.container_number):
				self.status = "Completed"
		if self.status == "Assigned":
			self.assigned_at = now_datetime()   
				
