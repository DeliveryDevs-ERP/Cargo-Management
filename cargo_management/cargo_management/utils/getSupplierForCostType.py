import frappe

def get_supplier(cost_type):
    item_id = frappe.db.get_value("FPL Cost Type", cost_type, "item_id")
    suppliers = frappe.db.get_values("Item Supplier", {"parent": item_id}, "supplier")
    if suppliers:
        return suppliers[0][0]
    return None 