"""Disposable native metadata upgrade checks; never run on a business site."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import frappe
from cargo_management.tests.isolated_fixtures import require_disposable,Fixtures


class TestUpgrade(unittest.TestCase):
    def setUp(self):
        require_disposable()
        frappe.set_user('Administrator')

    def test_repeat_reconciliation_preserves_fields_and_records(self):
        from cargo_management.setup import reconcile
        before=frappe.get_all('Custom Field',fields=['*'],order_by='name')
        f=Fixtures()
        records={key:frappe.as_json(f.get(key).as_dict()) for key in ('company1','customer','item-1','booking-Road-Domestic')}
        reconcile();reconcile()
        self.assertEqual(before,frappe.get_all('Custom Field',fields=['*'],order_by='name'))
        self.assertEqual(records,{key:frappe.as_json(f.get(key).as_dict()) for key in records})

    def test_incompatible_existing_field_is_rejected(self):
        from cargo_management.release_metadata import reconcile
        get_meta=frappe.get_meta
        fake=deepcopy(get_meta('Purchase Invoice'))
        fake.get_field('custom_train_number').fieldtype='Text'
        with patch('frappe.get_meta',side_effect=lambda name,*a,**kw:fake if name=='Purchase Invoice' else get_meta(name,*a,**kw)):
            with self.assertRaisesRegex(frappe.ValidationError,'metadata conflict'):reconcile()
        self.assertEqual(get_meta('Purchase Invoice').get_field('custom_train_number').fieldtype,'Data')

    def test_legacy_location_classifier_transition_preserves_blanks(self):
        from cargo_management.location import reconcile_location_type
        name=frappe.db.get_value('Custom Field',{'dt':'Location','fieldname':'custom_location_type'},'name')
        field=frappe.get_doc('Custom Field',name)
        original=field.as_dict()
        location=Fixtures().get('location-1')
        prior=location.custom_location_type
        try:
            field.fieldtype='Data';field.options='';field.save()
            frappe.db.set_value('Location',location.name,'custom_location_type',None,update_modified=False)
            reconcile_location_type()
            self.assertEqual(frappe.get_meta('Location').get_field('custom_location_type').fieldtype,'Select')
            self.assertIsNone(frappe.db.get_value('Location',location.name,'custom_location_type'))
            frappe.db.set_value('Location',location.name,'custom_location_type','Unverified',update_modified=False)
            with self.assertRaisesRegex(frappe.ValidationError,'review'):reconcile_location_type()
        finally:
            frappe.db.set_value('Location',location.name,'custom_location_type',prior,update_modified=False)
            field=frappe.get_doc('Custom Field',name)
            for key in ('fieldtype','options','reqd','allow_in_quick_entry','mandatory_depends_on','description'):
                field.set(key,original.get(key))
            field.save()
            frappe.db.commit()

    def test_unrecognized_field_order_preserves_its_customization(self):
        from cargo_management.release_metadata import reconcile
        name=frappe.db.get_value('Property Setter',{'doc_type':'Booking Order','property':'field_order'},'name')
        original=frappe.db.get_value('Property Setter',name,'value')
        order=json.loads(original)
        order[0],order[1]=order[1],order[0]
        try:
            frappe.db.set_value('Property Setter',name,'value',json.dumps(order),update_modified=False)
            frappe.clear_cache(doctype='Booking Order')
            with self.assertRaises(frappe.ValidationError):reconcile()
            self.assertEqual(json.loads(frappe.db.get_value('Property Setter',name,'value')),order)
        finally:
            frappe.db.set_value('Property Setter',name,'value',original,update_modified=False)
            frappe.db.commit()
            frappe.clear_cache(doctype='Booking Order')
