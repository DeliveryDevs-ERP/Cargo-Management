# Copyright (c) 2024, Osama and contributors
# For license information, please see license.txt

from cargo_management.cargo_management.utils.Update_JOB_Container_FO_Status import updateJobStatus
from cargo_management.cargo_management.utils.revert_JOB_Container_FO_Status import revertJobStatus
from cargo_management.cargo_management.utils.api import create_invoice
from frappe.utils import now_datetime, getdate, get_link_to_form
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
		job_name: DF.Data | None
		job_start_location: DF.Link | None
		job_type: DF.Link | None
		sales_order_number: DF.Data | None
		status: DF.Literal["", "Draft", "Assigned", "Completed", "Cancelled"]
	# end: auto-generated types

	def validate(self):
		if self.status == "Completed":
			if self.job_name == "Gate In" and not self.gate_in:
				if revertJobStatus(self.name, self.freight_order_id, self.container_number):
					self.status = "Assigned"
			if self.job_name == "Gate Out" and not self.gate_out:
				if revertJobStatus(self.name, self.freight_order_id, self.container_number):
					self.status = "Assigned"

		if (self.gate_in or self.gate_out) and self.status != "Completed":
			if updateJobStatus(self.name, self.freight_order_id, self.container_number):
				self.status = "Completed"
		if self.status == "Assigned":
			self.assigned_at = now_datetime()

		self.create_purchase_invoice()
		if len(self.expenses) > 0:
			self.send_expense_invoice_notification()

	def send_expense_invoice_notification(self):
		booking_order = self.sales_order_number or frappe.db.get_value("FPL Containers", self.container_number, "booking_order_id")
		sales_order = frappe.db.get_value("Sales Order", {"custom_booking_order_id": booking_order}, "name")
		recipient_emails = [
			user["email"] for user in frappe.get_all(
				"User",
				filters={"role": "Accounts Manager"},
				fields=["email"]
			) if user.get("email")
		]

		if not recipient_emails:
			frappe.msgprint("No Accounts Managers found with valid email addresses.")
			return

		pending_expenses = []
		for expense in self.expenses:
			if expense.invoiced_ == 1 and not expense.sales_invoice_no:
				pending_expenses.append(expense)

		if not pending_expenses:
			return  

		job_link = get_link_to_form("FPLYardJob", self.name)

		rows = ""
		for expense in pending_expenses:
			rows += f"""
				<tr>
					<td>{expense.expense_type}</td>
					<td>{expense.amount}</td>
				</tr>
			"""

		table_html = f"""
			<table class="panel-header" border="0" cellpadding="0" cellspacing="0" width="100%">
				<tr height="10"></tr>
				<tr>
					<td width="15"></td>
					<td>
						<div class="text-medium text-muted">
							<h2>Please create Sales Invoice for Job: {self.name}</h2>
						</div>
					</td>
					<td width="15"></td>
				</tr>
				<tr height="10"></tr>
			</table>

			<table class="panel-body" border="0" cellpadding="0" cellspacing="0" width="100%">
				<tr height="10"></tr>
				<tr>
					<td width="15"></td>
					<td>
						<div>
							<ul class="list-unstyled" style="line-height: 1.7">
								<li><b>Sales Order:</b> {sales_order}</li>
								<li><b>Booking Order:</b> {booking_order}</li>
								<li><b>Job Document:</b> {job_link}</li>
							</ul>
							<br>
							<table border="1" cellpadding="5" cellspacing="0" style="width:100%; border-collapse: collapse;">
								<thead style="background: #f0f0f0;">
									<tr>
										<th>Expense Type</th>
										<th>Amount</th>
									</tr>
								</thead>
								<tbody>
									{rows}
								</tbody>
							</table>
						</div>
					</td>
					<td width="15"></td>
				</tr>
				<tr height="10"></tr>
			</table>
		"""
		frappe.sendmail(
			recipients=recipient_emails,
			subject=f"Pending Sales Invoice for Job: {self.name}",
			message=table_html
		)

	def create_purchase_invoice(self):
		default_company = frappe.defaults.get_user_default("company")
		for expense in self.expenses:
			if expense.purchase_invoiced_created == 0:
				item = frappe.get_value("FPL Cost Type", expense.expense_type, 'item_id')
				BO = frappe.get_value("FPL Freight Orders", self.freight_order_id, 'sales_order_number')
				if item:
					code = create_invoice(
						container_number=expense.container_number,
						FO=self.freight_order_id,
						yard=self.name,
						BO=BO,
						items=[{
							"item_code": item,
							"qty": 1,
							"rate": expense.amount	
						}],
						supplier=expense.client,
						company=default_company
					)
					if code:
						expense.purchase_invoiced_created = 1
						expense.purchase_invoice_no = code