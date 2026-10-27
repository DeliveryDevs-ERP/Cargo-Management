
# import click
import frappe
from frappe import _


def before_install():
    frappe.msgprint("Before Install: Setting up Cargo Management.")


def after_install():
    initialize_trasnport_mode()
    frappe.db.commit()  # nosemgrep: frappe-manual-commit - persist initial setup data created in after_install

def initialize_trasnport_mode():
    print("HH")
