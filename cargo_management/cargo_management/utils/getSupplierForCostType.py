import frappe

def get_supplier(cost_type, company=None):
    from cargo_management.cargo_management.utils.configuration import validate_binding
    cost = validate_binding('FPL Cost Type', cost_type, company) if company else frappe.get_doc('FPL Cost Type', cost_type)
    if cost.get('cargo_supplier'):
        return cost.cargo_supplier
    item_id = frappe.db.get_value("FPL Cost Type", cost_type, "item_id")
    suppliers = frappe.db.get_values("Item Supplier", {"parent": item_id}, "supplier")
    suppliers = sorted({row[0] for row in suppliers if row[0]})
    if len(suppliers) > 1:
        frappe.throw('Cargo Cost Type requires an explicit Supplier; the Item has multiple suppliers.')
    if suppliers:
        return suppliers[0]
    return None
