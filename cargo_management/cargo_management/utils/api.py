import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.utils import cstr, flt, today, add_months
from frappe.auth import LoginManager
import json

def create_invoice(**kwargs):
    try:
        data = kwargs
        # if data.get("crm_bill_no"):
            # if frappe.db.exists(
            #     "Purchase Invoice", {"crm_bill_no": data.get("crm_bill_no")}
            # ):
            #     return gen_response(500, "Invoice already exists")
        invoice_doc = frappe.new_doc("Purchase Invoice")
        # invoice_doc.taxes_and_charges = "General Tax Template - Fi"
        invoice_doc.update(data)
        
        #
        if data.get("container_number"):
            invoice_doc.remarks = frappe.get_value('FPL Containers', data.get("container_number"), 'container_number')
        if data.get("train_no"):
            invoice_doc.custom_train_number = data.get("train_no")
        if data.get("movement_type"):
            invoice_doc.custom_movement_type = data.get("movement_type")  
        if data.get("FO"):
            invoice_doc.freight_order = data.get("FO")  
        if data.get("BO"):
            invoice_doc.booking_order = data.get("BO")
        if data.get("Road"):
            invoice_doc.fplroadjob = data.get("Road")
        if data.get("yard"):
            invoice_doc.fplyardjob = data.get("yard")
        if data.get("CS"):
            invoice_doc.perform_cross_stuff = data.get("CS")
        if data.get("PM"):
            invoice_doc.fpl_perform_middle_mile = data.get("PM")
            
            
        # if invoice_doc.get("sales_partner"):
        #     if not frappe.db.exists("Sales Partner", invoice_doc.get("sales_partner")):
        #         sales_partner = frappe.get_all(
        #             "Sales Partner",
        #             filters={"partner_name": invoice_doc.get("sales_partner")},
        #             fields=["name"],
        #         )
        #         if len(sales_partner) >= 1:
        #             invoice_doc.update({"sales_partner": sales_partner[0].name})
        # if data.get("sales_person_code"):
        #     sales_person = frappe.db.get_value(
        #         "Sales Person",
        #         {"sales_person_code": data.get("sales_person_code")},
        #         "name",
        #     )
        #     if sales_person:
        #         invoice_doc.append(
        #             "sales_team",
        #             dict(
        #                 sales_person=sales_person,
        #                 allocated_percentage=100,
        #                 commission_rate=0,
        #                 incentives=data.get("sales_person_commission"),
        #             ),
        #         )
        if invoice_doc.taxes_and_charges:
            tax_template_doc = frappe.get_doc(
                "Purchase Taxes and Charges Template", invoice_doc.taxes_and_charges
            )
            if tax_template_doc:
                for row in tax_template_doc.taxes:
                    invoice_doc.append(
                        "taxes",
                        dict(
                            account_head=row.get("account_head"),
                            charge_type=row.get("charge_type"),
                            rate=row.get("rate"),
                            description=row.get("description"),
                        ),
                    )
        for item in invoice_doc.get("items"):
            if (
                frappe.db.get_value(
                    "Item", item.get("item_code"), "enable_deferred_revenue"
                )
                == 1
            ):
                item.enable_deferred_revenue = 1
                item.deferred_revenue_account = frappe.db.get_value(
                    "Item", item.get("item_code"), "deferred_revenue_account"
                )
                item.service_start_date = today()
                no_of_months = frappe.db.get_value(
                    "Item", item.get("item_code"), "no_of_months"
                )
                if no_of_months:
                    item.service_end_date = add_months(
                        today(),
                        frappe.db.get_value(
                            "Item", item.get("item_code"), "no_of_months"
                        ),
                    )

        # invoice_doc.customer = data.get("customer")
        # invoice_doc.company = data.get("company")
        # invoice_doc.due_date = data.get("due_date")
        # items = data.get("items")
        # for item in items:
        #     invoice_doc.append(
        #         "items",
        #         {
        #             "item_code": item.get("item_code"),
        #             "qty": item.get("qty"),
        #             "rate": item.get("rate"),
        #         },
        #     )
        res = invoice_doc.insert()
        if data.get("total_commission"):
            res.commission_rate = (flt(data.get("total_commission")) * 100) / flt(
                res.grand_total
            )
            res.total_commission = data.get("total_commission")
        # res.submit()
        gen_response(200, "Invoice Created Successfully", res)
        return invoice_doc.name
    except Exception as exec:
        frappe.db.rollback()
        frappe.log_error(title="Midway Error Log", message=frappe.get_traceback())
        gen_response(500, cstr(exec))
        return None



def gen_response(status, message, data=[]):
    frappe.response["http_status_code"] = status
    if status == 500:
        frappe.response["message"] = BeautifulSoup(str(message)).get_text()
    else:
        frappe.response["message"] = message
    frappe.response["data"] = data