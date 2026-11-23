"""Preserve Cargo notification channels while filtering recipients by real access."""
import frappe

NAMES={'Expenses Intimation','Over Expenses Intimation'}


class CargoNotificationRecipients:
    def get_list_of_recipients(self, doc, context):
        recipients=super().get_list_of_recipients(doc,context)
        if self.name not in NAMES:
            return recipients
        def allowed(email):
            user=frappe.db.get_value('User',{'email':email,'enabled':1},'name')
            return bool(user and frappe.has_permission(doc.doctype,'read',doc=doc,user=user)
                        and (not doc.get('custom_booking_order') or frappe.has_permission('Booking Order','read',doc=doc.custom_booking_order,user=user)))
        return tuple([email for email in group if allowed(email)] for group in recipients)
