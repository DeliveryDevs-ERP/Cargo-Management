"""Native synthetic accounting checks, guarded to a fresh disposable database."""
import frappe
from cargo_management.tests.isolated_fixtures import RollbackCase,make_booking


class TestFinancialIntegrations(RollbackCase):
    def test_native_sales_purchase_posting_and_reversals(self):
        booking=make_booking(self.f,self.uid,selected_labels=['Long Haul'])
        invoice=frappe.get_doc('Sales Invoice',booking.create_and_submit_sales_invoice())
        freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
        job=frappe.get_doc('FPLRoadJob',freight.jobs[0].job_id)
        purchase=frappe.get_doc('Purchase Invoice',job.expenses[0].purchase_invoice_no)
        for doc in (invoice,purchase):
            doc.submit()
            rows=frappe.get_all('GL Entry',filters={'voucher_type':doc.doctype,'voucher_no':doc.name},fields=['debit','credit'])
            self.assertTrue(rows,doc.doctype)
            self.assertAlmostEqual(sum(r.debit for r in rows),sum(r.credit for r in rows))
            self.assertEqual(doc.docstatus,1)
            doc.cancel()
            self.assertEqual(doc.docstatus,2)
            rows=frappe.get_all('GL Entry',filters={'voucher_type':doc.doctype,'voucher_no':doc.name},fields=['debit','credit','is_cancelled'])
            self.assertTrue(rows)
            self.assertAlmostEqual(sum(r.debit for r in rows),sum(r.credit for r in rows))

    def test_extra_invoice_claim_submit_cancel_preserves_expense_identity(self):
        from cargo_management.cargo_management.api.expense_billing import fetch_expenses_items
        booking=make_booking(self.f,self.uid,selected_labels=['Long Haul'])
        freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
        job=frappe.get_doc('FPLRoadJob',freight.jobs[0].job_id)
        expense=job.expenses[0]
        expense.invoiced_=1;job.save()
        base=frappe.get_doc('Sales Invoice',booking.create_and_submit_sales_invoice());base.submit()
        items=fetch_expenses_items(base.name)['expenses'];self.assertEqual(len(items),1)
        extra=frappe.copy_doc(base);extra.is_debit_note=1;extra.return_against=base.name
        extra.set('items',items);extra.insert();extra.submit()
        self.assertEqual(frappe.db.get_value('Expenses cdt',expense.name,'sales_invoice_no'),extra.name)
        self.assertEqual(fetch_expenses_items(base.name)['expenses'],[])
        extra.cancel()
        self.assertFalse(frappe.db.get_value('Expenses cdt',expense.name,'sales_invoice_no'))
        self.assertTrue(frappe.db.exists('Expenses cdt',expense.name))
        self.assertEqual(len(fetch_expenses_items(base.name)['expenses']),1)
