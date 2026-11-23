"""Non-posting regressions for the reviewed remediation and unresolved policies."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import frappe
from cargo_management.location import LOCATION_TYPES, validate_location
from cargo_management.release_metadata import merge_field_order
from cargo_management.cargo_management.utils.billing import (
    allocate_total, billing_inputs, item_values, prepare_booking, quantity,
)
from cargo_management.cargo_management.utils.rail_charges import select_tariff


def reject(message, *args, **kwargs):
    raise frappe.ValidationError(message)


class TestReviewedMetadata(unittest.TestCase):
    def test_known_layout_repair_preserves_foreign_slots_and_fields(self):
        actual = merge_field_order(['a','foreign','c','b','added'], ['a','foreign','c','b'],
                                   ['a','b','c'], [['a','c','b']])
        self.assertEqual(actual, ['a','foreign','b','c','added'])
        self.assertEqual(merge_field_order(actual, actual, ['a','b','c']), actual)

    def test_unreviewed_layout_and_missing_fields_fail_closed(self):
        for current,prior in [(['a','b','c'],['b','a','c']), (['a','b'],['a','b'])]:
            with self.assertRaises(ValueError):merge_field_order(current,prior,['a','b','c'])

    def test_invoice_columns_are_defaults_without_user_setting_writes(self):
        path=Path(__file__).parents[1]/'cargo_management/doctype/expenses_cdt/expenses_cdt.json'
        fields={f['fieldname']:f for f in json.loads(path.read_text())['fields']}
        self.assertEqual(fields['purchase_invoice_no']['in_list_view'],1)
        self.assertEqual(fields['sales_invoice_no']['in_list_view'],1)
        self.assertEqual(fields['amount']['fieldtype'],'Currency')
        self.assertFalse(fields['amount'].get('precision'))

    def test_location_creation_and_grandfathered_blanks(self):
        def doc(value,new=False,old=None):
            d=frappe._dict(custom_location_type=value)
            d.is_new=lambda:new;d.get_doc_before_save=lambda:old
            return d
        with patch('cargo_management.location._',side_effect=lambda s:s),patch.object(frappe,'throw',side_effect=reject):
            for value in LOCATION_TYPES:validate_location(doc(value,True))
            validate_location(doc('',False,frappe._dict(custom_location_type='')))
            for candidate in (doc('',True),doc('Unverified',True),doc('',False,frappe._dict(custom_location_type='Yard'))):
                with self.assertRaises(frappe.ValidationError):validate_location(candidate)


class TestRailNumericalEvidence(unittest.TestCase):
    """Synthetic prices preserve the overlap geometry without exposing contracts."""
    def setUp(self):
        self.rows=[dict(name=name,wagon_type='Large',container_count=1,container_count_40=1,
            avg_weight=w20,avg_weight_40=w40,rate_20=r20,rate_40=r40,cargo_priority=p)
            for name,w20,w40,r20,r40,p in [('Example-A',40,30,100,200,30),
                ('Example-B',30,30,150,175,20),('Example-C',20,40,110,210,10)]]

    def test_synthetic_thresholds_container_prices_and_wagon_totals(self):
        for weights,name,prices in [((25,25),'Example-B',(150,175)),((20,30),'Example-C',(110,210)),
                ((30,30),'Example-B',(150,175)),((40,30),'Example-A',(100,200)),((20,40),'Example-C',(110,210))]:
            with self.subTest(weights=weights):
                result=select_tariff(self.rows,'Large',1,1,*weights)
                self.assertEqual(result['name'],name)
                self.assertEqual((result['rate_20'],result['rate_40']),prices)
                self.assertEqual(sum(prices),{'Example-A':300,'Example-B':325,'Example-C':320}[name])
        source=lambda a,b:sum(r['rate_20']+r['rate_40'] for r in self.rows if r['avg_weight']>=a and r['avg_weight_40']>=b)
        self.assertEqual(source(25,25),625)
        self.assertEqual(source(20,30),945)

    def test_invalid_boundaries_ties_missing_and_nonfinite_inputs(self):
        for counts,weights in [((1,1),(40.01,30)),((1,1),(0,20)),((1.5,1),(20,20)),((0,0),(0,0)),((1,1),('NaN',30))]:
            with self.assertRaises(ValueError):select_tariff(self.rows,'Large',*counts,*weights)
        for p in (0,10):
            rows=deepcopy(self.rows)
            for r in rows:r['cargo_priority']=p
            with self.assertRaises(ValueError):select_tariff(rows,'Large',1,1,20,30)
        rows=self.rows+[dict(self.rows[1],name='duplicate',cargo_priority=1)]
        with self.assertRaises(ValueError):select_tariff(rows,'Large',1,1,25,25)


class TestBillingConservation(unittest.TestCase):
    def test_original_formulas_and_both_recorded_policy_mappings(self):
        row=frappe._dict(qty=2,avg_weight=20,bag_qty=100,bag_weight=50,rate=100,
            amount=4000,cargo_effective_rate=100,cargo_native_amount=4000,name='new-test-row')
        for basis,billable in [('Per Container',2),('Per Bag',100),('Per Weight(Ton)',40),('Nos',2)]:
            row.rate_type=basis
            self.assertEqual(quantity(row),billable)
            self.assertEqual(item_values(row,1)['qty'],billable)
        row.rate_type='Per Weight(Ton)'
        self.assertEqual(item_values(row,0)['qty'],100)
        self.assertEqual(item_values(row,0)['amount'],4000)

    def test_bag_and_revenue_conservation_including_unequal_and_rounding_cases(self):
        for total,count,precision in [('100',1,0),('100',2,0),('100',3,0),('2',4,0),
                                      ('0',3,0),('0.02',4,2),('100.01',3,2)]:
            result=[allocate_total(total,count,i,precision) for i in range(count)]
            self.assertEqual(sum(result),Decimal(total))
            self.assertTrue(all(v>=0 for v in result))

    def test_bag_weight_question_is_explicitly_characterized_without_changing_policy(self):
        # Conditional proposal only: 50 kg/bag and ROW-TOTAL bags still require business evidence.
        for bags,count,kg in [(100,1,'50'),(100,2,'50'),(100,3,'50'),(7,3,'0.125'),(0,2,'50')]:
            allocated=[allocate_total(bags,count,i,0) for i in range(count)]
            proposed=[b*Decimal(kg)/1000 for b in allocated]
            self.assertEqual(sum(proposed),Decimal(bags)*Decimal(kg)/1000)
        inherited_per_freight=Decimal(100)*50/1000
        self.assertEqual(inherited_per_freight,5)
        self.assertEqual(sum(allocate_total(100,2,i,0)*50/1000 for i in range(2)),5)
        self.assertEqual(inherited_per_freight*2,10)

    def test_input_identity_ignores_serialization_without_losing_real_changes(self):
        a=frappe._dict(rate_type='Per Container',qty=2,rate=100,avg_weight=20,bag_qty=0,bag_weight=0)
        b=frappe._dict(rate_type='Per Container',qty=2.0,rate=Decimal('100.000000000'),avg_weight=20.0,bag_qty=None,bag_weight=0.0)
        self.assertEqual(billing_inputs(a),billing_inputs(b))
        b.rate=101
        self.assertNotEqual(billing_inputs(a),billing_inputs(b))

    def test_unchanged_native_roundtrip_preserves_approved_override_and_recorded_hash(self):
        old=frappe._dict(name='row',rate_type='Per Container',qty=2,rate=100,avg_weight=20,bag_qty=0,bag_weight=0,
            amount=300,cargo_billing_override=1,cargo_override_amount=300,cargo_override_reason='Approved QA override',
            cargo_billing_input_hash='recorded-int-spelling-hash',cargo_discrepancy_acknowledged=1)
        row=deepcopy(old);row.rate=100.0;row.qty=2.0
        doc=frappe._dict(company='test-company',cargo_billing_version=1,cargo_details=[row],docstatus=0)
        doc.get_doc_before_save=lambda:frappe._dict(company='test-company',cargo_billing_version=1,cargo_details=[old])
        meta=SimpleNamespace(get_field=lambda name:frappe._dict(fieldname='rate',fieldtype='Currency',precision='2'))
        db=SimpleNamespace(get_value=lambda dt,*args,**kwargs:'PKR' if dt=='Company' else (0,0))
        with patch.object(frappe,'db',db),patch.object(frappe,'get_meta',return_value=meta),\
                patch('cargo_management.cargo_management.utils.billing._',side_effect=lambda s:s),\
                patch.object(frappe,'only_for'),patch.object(frappe,'throw',side_effect=reject):
            prepare_booking(doc)
            self.assertEqual(row.cargo_billing_input_hash,old.cargo_billing_input_hash)
            self.assertEqual(row.cargo_discrepancy_acknowledged,1)
            self.assertEqual(row.cargo_native_amount,300)
            row.rate=101
            with self.assertRaises(frappe.ValidationError):prepare_booking(doc)

    def test_unchanged_contract_keeps_native_values_after_framework_precision_changes(self):
        old=frappe._dict(name='row',cargo_type='test-item',rate_type='Per Container',qty=2,rate=1.234,
            avg_weight=20,bag_qty=0,bag_weight=0,amount=2.46,cargo_billing_override=0,
            cargo_effective_rate=1.23,cargo_native_amount=2.46,cargo_billing_input_hash='original-contract-hash')
        row=deepcopy(old);row.cargo_effective_rate=99;row.cargo_native_amount=198
        before=frappe._dict(company='test-company',cargo_billing_version=1,cargo_details=[old])
        doc=frappe._dict(company='test-company',cargo_billing_version=1,cargo_details=[row],docstatus=0)
        doc.get_doc_before_save=lambda:before
        meta=SimpleNamespace(get_field=lambda name:frappe._dict(fieldname='rate',fieldtype='Currency',precision='3'))
        db=SimpleNamespace(get_value=lambda dt,*args,**kwargs:'PKR' if dt=='Company' else (0,0))
        with patch.object(frappe,'db',db),patch.object(frappe,'get_meta',return_value=meta):
            prepare_booking(doc)
        self.assertEqual(row.cargo_effective_rate,1.23)
        self.assertEqual(row.cargo_native_amount,2.46)
        self.assertEqual(row.cargo_billing_input_hash,'original-contract-hash')



if __name__ == "__main__": unittest.main()
