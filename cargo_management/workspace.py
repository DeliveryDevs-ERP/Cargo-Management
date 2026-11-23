"""Resolve Cargo shortcut services by behavior rather than source-site IDs."""
import json
import frappe


def reconcile(doc=None, method=None):
    if not frappe.db.exists('Workspace', 'Cargo Management'):
        return
    from cargo_management.cargo_management.utils.services import service_names
    for row in frappe.get_all('Workspace Shortcut', filters={'parent': 'Cargo Management'}, fields=['name','label','link_to','stats_filter']):
        label = row.label.strip()
        if label in ('Empty Pickup','Empty Return','First Mile','Middle Mile','Last Mile','Long Haul','Short Haul','Gate In','Gate Out','Cross Stuff'):
            filters = [[row.link_to, 'job_type', 'in', service_names(label), False],
                       [row.link_to, 'status', '=', 'Assigned', False]]
            if frappe.get_meta(row.link_to).has_field('cargo_retired'):
                filters.append([row.link_to, 'cargo_retired', '=', 0, False])
            encoded = json.dumps(filters)
            if row.stats_filter != encoded:
                frappe.db.set_value('Workspace Shortcut', row.name, 'stats_filter', encoded, update_modified=False)
    frappe.clear_cache(doctype='Workspace')
