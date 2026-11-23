"""Install schema only; business masters and operational routing are user configuration."""
import frappe


def before_install():
    if 'erpnext' not in frappe.get_installed_apps():
        frappe.throw('Cargo Management requires the existing ERPNext installation.')


def after_install():
    from cargo_management.setup import reconcile
    reconcile()
