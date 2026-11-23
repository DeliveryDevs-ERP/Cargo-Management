"""Field-order portability regressions with fully mocked metadata and writes.

No site, database connection, schema change or fixture is needed. Run inside a
compatible Bench Python environment with unittest, not through bench run-tests.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import frappe
from cargo_management import release_metadata as release


class FieldOrderPortability(unittest.TestCase):
    def run_case(self,doctype,transform,invalid=False):
        requirements=json.loads((Path(release.__file__).parent/'release_requirements.json').read_text())
        orders={r['doctype']:list(r['field_order'])for r in requirements['field_orders']}
        metas={};written={}
        for dt,definitions in release.MISSING_FIELDS.items():
            fields=[frappe._dict(d)for d in definitions]
            metas[dt]=SimpleNamespace(fields=fields,get_field=lambda name,fields=fields:next((f for f in fields if f.fieldname==name),None))
        for dt,names in orders.items():
            fields=metas[dt].fields if dt in metas else []
            fields.extend(frappe._dict(fieldname=n,fieldtype='Data')for n in names if n not in {f.fieldname for f in fields})
            if dt=='FPL Freight Orders':
                fields.extend(frappe._dict(fieldname=n,fieldtype='Data')for n in ('cargo_request','cargo_cross_stuff_performance')if n not in {f.fieldname for f in fields})
            if dt==doctype:fields.append(frappe._dict(fieldname='custom_other_app_probe',fieldtype='Data'))
            metas[dt]=SimpleNamespace(fields=fields,get_field=lambda name,fields=fields:next((f for f in fields if f.fieldname==name),None))
        metas['Sales Order']=SimpleNamespace(get_field=lambda name:frappe._dict(read_only=1))
        priors={dt:json.dumps(names)for dt,names in orders.items()};priors[doctype]=transform(list(orders[doctype]))
        def lookup(dt,filters,*args,**kwargs):
            self.assertEqual(dt,'Property Setter')
            return frappe._dict(name='owned-mock',value=priors[filters['doc_type']])
        def write(dt,field,prop,value,*args,**kwargs):
            self.assertEqual(prop,'field_order');written[dt]=json.loads(value)
        def reject(message,*args,**kwargs):raise frappe.ValidationError(message)
        # Replacing the local proxy itself avoids initializing any site/database.
        with patch.object(frappe,'db',SimpleNamespace(get_value=lookup)),\
             patch.object(frappe,'get_meta',side_effect=lambda name:metas[name]),\
             patch.object(release,'_',side_effect=lambda message:message),\
             patch.object(frappe,'throw',side_effect=reject),\
             patch('frappe.custom.doctype.custom_field.custom_field.create_custom_fields')as create,\
             patch('frappe.custom.doctype.property_setter.property_setter.make_property_setter',side_effect=write),\
             patch.object(release,'sync_owned_documents'):
            if invalid:
                with self.assertRaises(frappe.ValidationError):release.reconcile()
            else:release.reconcile()
            create.assert_not_called()
        return orders,written

    def test_new_foreign_field_is_appended_without_conflict(self):
        orders,written=self.run_case('Booking Order',json.dumps)
        self.assertEqual(written['Booking Order'],orders['Booking Order']+['custom_other_app_probe'])

    def test_existing_foreign_field_position_is_preserved(self):
        def prior(names):return json.dumps(names[:2]+['custom_other_app_probe']+names[2:])
        orders,written=self.run_case('Booking Order',prior)
        # An already correct order need not cause a write.
        self.assertNotIn('Booking Order',written)

    def test_known_lineage_fields_are_added_without_losing_foreign_field(self):
        lineage={'cargo_request','cargo_cross_stuff_performance'}
        def prior(names):return json.dumps([n for n in names if n not in lineage]+['custom_other_app_probe'])
        orders,written=self.run_case('FPL Freight Orders',prior)
        result=written['FPL Freight Orders']
        self.assertEqual([n for n in result if n in orders['FPL Freight Orders']],orders['FPL Freight Orders'])
        self.assertIn('custom_other_app_probe',result)
        self.assertTrue(lineage.issubset(result))

    def test_reordered_cargo_fields_are_rejected(self):
        def prior(names):names[0],names[1]=names[1],names[0];return json.dumps(names)
        self.run_case('Booking Order',prior,invalid=True)

    def test_duplicate_fields_are_rejected(self):
        self.run_case('Booking Order',lambda names:json.dumps(names+[names[0]]),invalid=True)

    def test_unknown_fields_are_rejected(self):
        self.run_case('Booking Order',lambda names:json.dumps(names+['not_a_current_field']),invalid=True)

    def test_malformed_order_is_rejected(self):
        for value in ('not-json','{}','[1]','null'):
            with self.subTest(value=value):self.run_case('Booking Order',lambda names:value,invalid=True)


if __name__=='__main__':unittest.main(verbosity=2)
