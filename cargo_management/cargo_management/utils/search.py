"""Frappe Link-query argument and permission handling shared by Cargo queries."""
import frappe
from frappe.utils import cint


def search_arguments(args, kwargs):
    values = dict(zip(('doctype','txt','searchfield','start','page_len','filters'),args))
    values.update(kwargs)
    filters = values.get('filters') or {}
    if isinstance(filters,str): filters=frappe.parse_json(filters)
    return frappe._dict(txt=values.get('txt') or '',start=max(0,cint(values.get('start',0))),
        page_len=max(0,cint(values.get('page_len',20))),filters=frappe._dict(filters))


def require_read(doctype, name=None):
    if not frappe.has_permission(doctype,'read',doc=name):
        frappe.throw(frappe._('Not permitted to read {0}').format(doctype),frappe.PermissionError)


def results(sql, parameters, doctype, arguments):
    require_read(doctype)
    rows=frappe.db.sql(sql,parameters)
    rows=[row for row in rows if frappe.has_permission(doctype,'read',doc=row[0])]
    return rows[arguments.start:] if arguments.page_len==0 else rows[arguments.start:arguments.start+arguments.page_len]
