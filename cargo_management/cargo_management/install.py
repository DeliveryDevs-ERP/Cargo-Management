
# import click
import frappe
from frappe import _



def after_install():
    initialize_trasnport_mode()
    frappe.db.commit()

def initialize_trasnport_mode():
    print("HH")