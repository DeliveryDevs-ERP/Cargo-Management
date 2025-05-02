import frappe

@frappe.whitelist()
def fetch_expenses_items(sales_invoice_number):
    sales_order = frappe.get_value("Sales Invoice Item", {"parent": sales_invoice_number}, "sales_order")
    booking_order = frappe.get_value("Sales Order", {"name": sales_order}, "custom_booking_order_id")
    expenses = []

    child_tables = [
        {"doctype": "FPLRoadJob", "fieldname": "expenses"},
        {"doctype": "FPL Perform Middle Mile", "fieldname": "expenses"},
        {"doctype": "Perform Cross Stuff", "fieldname": "expenses"},
        {"doctype": "FPLYardJob", "fieldname": "expenses"},
    ]

    default_income_account = frappe.get_value(
        "Company",
        frappe.db.get_value("Booking Order", {"name": booking_order}, "company"),
        "default_income_account"
    )

    for table in child_tables:
        records = get_filtered_records_by_container(table["doctype"], table["fieldname"], booking_order)
        for doc in records:
            for expense in doc.get(table["fieldname"], []):
                if expense.invoiced_ == 1 and not expense.sales_invoice_no:
                    item = frappe.get_value(
                        "FPL Cost Type",
                        {"name": expense.expense_type},
                        "item_id"
                    )

                    if not item:
                        frappe.throw(f"Item not found for expense type {expense.expense_type} in FPL Cost Type.")

                    item_details = frappe.get_value(
                        "Item",
                        {"name": item},
                        ["item_name", "stock_uom"],
                        as_dict=True
                    )

                    if not item_details:
                        frappe.throw(f"Item details not found for item ID {item} in the Item doctype.")
                    
                    expenses.append({
                        "item_code": item,
                        "item_name": item_details.get("item_name"),
                        "uom": item_details.get("stock_uom"),
                        "qty": 1,
                        "rate": expense.amount,
                        "amount": expense.amount,
                        "description": f"Expense from {table['doctype']} - {doc.name} - {expense.name}",
                        "income_account": default_income_account,
                    })

    return {"expenses": expenses, "custom_booking_order": booking_order}


def get_filtered_records_by_container(doctype, fieldname, booking_order):
    matched_docs = []

    all_docs = frappe.get_all(doctype, fields=["name"])
    for entry in all_docs:
        doc = frappe.get_doc(doctype, entry["name"])
        child_rows = doc.get(fieldname, [])

        for row in child_rows:
            if not row.container_number:
                continue

            container_booking = frappe.db.get_value("FPL Containers", row.container_number, "booking_order_id")
            if container_booking == booking_order:
                matched_docs.append(doc)
                break

    return matched_docs
