import frappe

@frappe.whitelist()
def fetch_expenses_items(sales_invoice_number):
    sales_order = frappe.get_value("Sales Invoice Item", {"parent": sales_invoice_number}, "sales_order")
    booking_order = frappe.get_value("Sales Order", {"name": sales_order}, "custom_booking_order_id")
    expenses = []
    child_tables = [
        {"doctype": "FPLRoadJob", "fieldname": "expenses"},
        {"doctype": "FPLYardJob", "fieldname": "expenses"},
        # Add more tables if necessary
    ]

    # Get the default income account from the Company
    default_income_account = frappe.get_value(
        "Company",
        frappe.db.get_value("Booking Order", {"name": booking_order}, "company"),
        "default_income_account"
    )

    for table in child_tables:
        # Get all Job records where the booking order matches
        records = frappe.get_all(
            table["doctype"],
            filters={"sales_order_number": booking_order},
            fields=["name"]
        )
        for record in records:
            doc = frappe.get_doc(table["doctype"], record["name"])
            for expense in doc.get(table["fieldname"], []):
                if expense.invoiced_ == 1:  # Check if the expense is for invoicing
                    # Fetch the item details from the FPL Cost Type
                    item = frappe.get_value(
                        "FPL Cost Type",
                        {"name": expense.expense_type},
                        "item_id"
                    )

                    if not item:
                        frappe.throw(
                            f"Item not found for expense type {expense.expense_type} in FPL Cost Type."
                        )

                    # Fetch the item_name and uom from the Item doctype
                    item_details = frappe.get_value(
                        "Item",
                        {"name": item},
                        ["item_name", "stock_uom"],
                        as_dict=True
                    )

                    if not item_details:
                        frappe.throw(
                            f"Item details not found for item ID {item} in the Item doctype."
                        )
                    
                    # Add the expense details to the expenses list
                    expenses.append({
                        "item_code": item,
                        "item_name": item_details.get("item_name"),
                        "uom": item_details.get("stock_uom"),
                        "qty": 1,
                        "rate": expense.amount,
                        "amount": 1 * expense.amount,
                        "description": expense.remarks or f"Expense from {table['doctype']} - {doc.name}",
                        "income_account": default_income_account,
                    })
    return {"expenses": expenses, "custom_booking_order": booking_order}
