import frappe
import re

@frappe.whitelist()
def update_expense_references(doc, method):
    """
    On Sales Invoice Submit:
    Parses each row's description to find the source doctype, parent name, and child table row name.
    Then updates the corresponding child table row with the current Sales Invoice's name.
    """
    for item in doc.items:
        description = item.description or ""
        # Expected format: "Expense from FPLRoadJob - First Mile-02251 - 6rn9bkb5i1"
        match = re.match(r"^Expense from (.+?) - (.+) - (\w+)$", description)
        if not match:
            frappe.throw(f"Invalid description format in row: '{description}'. Expected: 'Expense from <Doctype> - <Parent Name> - <Child Row ID>'")
            continue
        doctype, parent_name, child_row_name = match.groups()

        try:
            parent_doc = frappe.get_doc(doctype, parent_name)
        except frappe.DoesNotExistError:
            frappe.log_error(f"{doctype} named {parent_name} not found", "Update Expense Ref")
            continue

        updated = False
        for child_table_field in parent_doc.meta.get_table_fields():
            for row in parent_doc.get(child_table_field.fieldname):
                if row.name == child_row_name:
                    row.sales_invoice_no = doc.name
                    updated = True
                    break
            if updated:
                break

        if updated:
            parent_doc.save(ignore_permissions=True)
        else:
            frappe.log_error(
                f"Could not find child row {child_row_name} in {doctype} - {parent_name}",
                "Update Expense Ref"
            )
