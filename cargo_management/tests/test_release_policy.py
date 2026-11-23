"""Financial-policy regressions without database writes or invoice posting."""
from decimal import Decimal
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import frappe
from cargo_management.cargo_management.utils.billing import allocate_total, item_values, quantity
from cargo_management.cargo_management.utils.rail_charges import select_tariff, charge_key


def tariff(name, threshold20=0, threshold40=0, priority=0, count20=1, count40=1, rate20=100, rate40=200, category='Large'):
    return dict(name=name, wagon_type=category, container_count=count20, container_count_40=count40,
                avg_weight=threshold20, avg_weight_40=threshold40, cargo_priority=priority, rate_20=rate20, rate_40=rate40)


class TestRailPolicy(unittest.TestCase):
    def test_single_40_reference_is_preserved_without_invented_weight_predicate(self):
        row = tariff('single40', count20=0, rate20=0, rate40=325)
        for weight in (0, 20, 30, 100):
            self.assertEqual(select_tariff([row], 'Large', 0, 1, 0, weight)['rate_40'], 325)

    def test_single_20_small_and_large_unique_prices(self):
        for category, rate in [('Large', 325), ('Small', 290)]:
            row = tariff(category, count40=0, rate20=rate, rate40=0, category=category)
            self.assertEqual(select_tariff([row], category, 1, 0)['rate_20'], rate)

    def test_source_mixed_overlap_requires_explicit_policy(self):
        rows = [tariff('40/30',40,30), tariff('30/30',30,30), tariff('20/40',20,40)]
        with self.assertRaisesRegex(ValueError, 'priorities'):
            select_tariff(rows, 'Large', 1, 1, 20, 30)

    def test_unique_narrower_ceiling_preserves_its_prices(self):
        rows = [tariff('40/40',40,40), tariff('30/30',30,30,rate20=150,rate40=175)]
        self.assertEqual(select_tariff(rows,'Large',1,1,20,30)['name'],'30/30')

    def test_incomparable_priority_and_input_order(self):
        rows = [tariff('30/30',30,30,20), tariff('20/40',20,40,10)]
        for ordered in (rows, list(reversed(rows))):
            self.assertEqual(select_tariff(ordered,'Large',1,1,20,30)['name'],'20/40')

    def test_weight_boundaries_and_missing_weights(self):
        row = tariff('boundary',20,40)
        self.assertEqual(select_tariff([row],'Large',1,1,20,40)['name'],'boundary')
        for weights in [(20.00001,40),(20,40.00001),(0,30),(20,None),(-1,20),(float('nan'),20),(float('inf'),20)]:
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                select_tariff([row],'Large',1,1,*weights)

    def test_conflicting_duplicate_and_tied_priorities_fail_closed(self):
        for rows in [[tariff('a',20,40,1),tariff('b',20,40,2)],
                     [tariff('a',30,30,1),tariff('b',20,40,1)]]:
            with self.assertRaises(ValueError): select_tariff(rows,'Large',1,1,20,30)

    def test_single_size_duplicate_cannot_be_hidden_by_priority(self):
        with self.assertRaises(ValueError):
            select_tariff([tariff('a',count20=0,priority=1),tariff('b',count20=0,priority=2)],'Large',0,1)

    def test_counts_and_categories_are_exact(self):
        for counts in [(0,0),(-1,1),(1.5,1)]:
            with self.assertRaises(ValueError): select_tariff([], 'Large', *counts)
        with self.assertRaises(ValueError): select_tariff([tariff('large')],'Small',1,1,20,30)

    def test_charge_identity_deduplicates_station_matches_but_not_distinct_fees(self):
        self.assertEqual(charge_key('train','container','fee1'),charge_key('train','container','fee1'))
        self.assertNotEqual(charge_key('train','container','fee1'),charge_key('train','container','fee2'))
        self.assertNotEqual(charge_key('train','container','fee1'),charge_key('train','other','fee1'))


class TestBillingPolicy(unittest.TestCase):
    def test_native_uom_quantities_and_legacy_ton_contract(self):
        row = frappe._dict(qty=2, avg_weight=20, bag_qty=10, bag_weight=5, rate=100, amount=280,
                           cargo_effective_rate=100, cargo_native_amount=4000, name='owned-row')
        for rate_type, expected in [('Per Container',2),('Per Bag',10),('Per Weight(Ton)',40),('Nos',2),('custom generic',2)]:
            row.rate_type=rate_type
            self.assertEqual(quantity(row),expected)
            self.assertEqual(item_values(row,1)['qty'],expected)
        row.rate_type='Per Weight(Ton)'
        self.assertEqual(item_values(row,0)['qty'],10)
        self.assertEqual(item_values(row,0)['amount'],280)

    def test_original_rate_is_preserved_by_effective_override(self):
        row=frappe._dict(qty=2,rate_type='Per Container',rate=70,cargo_effective_rate=140,
                        cargo_native_amount=280,name='owned-row')
        self.assertEqual(item_values(row,1)['rate'],140)
        self.assertEqual(row.rate,70)

    def test_allocation_conserves_currency_bags_and_fractional_totals(self):
        for total,count,precision in [('100',3,2),('.02',4,2),('2',4,0),('2.5',2,0),('10',3,0),('0',4,2)]:
            values=[allocate_total(total,count,index,precision) for index in range(count)]
            self.assertEqual(sum(values),Decimal(total))
            self.assertTrue(all(value>=0 for value in values))


class TestExpenseOwnership(unittest.TestCase):
    """Exercise submitted-claim integrity without saving or posting documents."""
    parents = ('FPLRoadJob', 'FPLYardJob', 'Perform Cross Stuff', 'FPL Perform Middle Mile')

    def expense(self, claimed=True):
        return frappe._dict(name='expense-1', expense_type='cost-1', amount=7, client='supplier-1',
            container_number='allocation-1', purchase_invoice_no='PI-1', purchase_invoiced_created=1,
            sales_invoice_no='SI-1' if claimed else None, invoiced_=1,
            cargo_invoice_history='[{"invoice":"SI-1","action":"claimed"}]' if claimed else None,
            cargo_charge_key='native-charge-1', cargo_tariff='tariff-1')

    def document(self, doctype, expenses, new=False):
        doc = frappe._dict(doctype=doctype, name='parent-1', expenses=expenses, flags=frappe._dict())
        doc.is_new = lambda: new
        doc.meta = SimpleNamespace(has_field=lambda field: field in doc)
        return doc

    def validate(self, candidate, saved, existing_foreign_row=None):
        from cargo_management.permissions import validate_expense_history
        def reject(message, *args, **kwargs):
            raise frappe.ValidationError(message)
        with ExitStack() as stack:
            get_doc = stack.enter_context(patch.object(frappe, 'get_doc', return_value=saved))
            stack.enter_context(patch.object(frappe, 'db', SimpleNamespace(
                get_value=Mock(return_value=existing_foreign_row))))
            stack.enter_context(patch.object(frappe, 'throw', side_effect=reject))
            fixed = stack.enter_context(patch('cargo_management.expense_controls.initialize_fixed_costs'))
            context = stack.enter_context(patch('cargo_management.cargo_management.api.expense_billing.expense_context'))
            try:
                validate_expense_history(candidate)
            except frappe.ValidationError:
                fixed.assert_not_called()
                context.assert_not_called()
                raise
            if not candidate.is_new():
                get_doc.assert_called_once_with(candidate.doctype, candidate.name, for_update=True)
            context.assert_has_calls([unittest.mock.call(candidate, row) for row in candidate.expenses])

    def test_unchanged_claims_and_generated_charge_metadata_remain_valid(self):
        for doctype in self.parents:
            with self.subTest(doctype=doctype):
                saved = self.document(doctype, [self.expense()])
                self.validate(self.document(doctype, deepcopy(saved.expenses)), saved)

    def test_persisted_server_metadata_cannot_be_cleared_or_forged(self):
        for doctype in self.parents:
            for field in ('cargo_invoice_history', 'cargo_charge_key', 'cargo_tariff'):
                for replacement in (None, 'forged-value'):
                    with self.subTest(doctype=doctype, field=field, replacement=replacement):
                        saved = self.document(doctype, [self.expense()])
                        candidate = self.document(doctype, deepcopy(saved.expenses))
                        candidate.expenses[0][field] = replacement
                        with self.assertRaisesRegex(frappe.ValidationError, 'server|native|history'):
                            self.validate(candidate, saved)

    def test_new_rows_cannot_supply_server_metadata(self):
        for doctype in self.parents:
            for new_parent in (False, True):
                for field in ('cargo_invoice_history', 'cargo_charge_key', 'cargo_tariff'):
                    with self.subTest(doctype=doctype, new_parent=new_parent, field=field):
                        row = frappe._dict(name='new-expense', expense_type='cost-1', invoiced_=1)
                        row[field] = '[]' if field == 'cargo_invoice_history' else 'forged-value'
                        with self.assertRaises(frappe.ValidationError):
                            self.validate(self.document(doctype, [row], new_parent), self.document(doctype, []))

    def test_billability_is_immutable_only_while_sales_claim_is_active(self):
        for doctype in self.parents:
            with self.subTest(doctype=doctype):
                saved = self.document(doctype, [self.expense()])
                candidate = self.document(doctype, deepcopy(saved.expenses))
                candidate.expenses[0].invoiced_ = 0
                with self.assertRaises(frappe.ValidationError):
                    self.validate(candidate, saved)
                saved.expenses[0].sales_invoice_no = None
                # A released claim retains its history; billability is editable again.
                candidate.expenses[0].sales_invoice_no = None
                self.validate(candidate, saved)

    def test_new_plain_expense_and_preclaim_billability_are_allowed(self):
        for doctype in self.parents:
            with self.subTest(doctype=doctype):
                row = frappe._dict(name='new-expense', expense_type='cost-1', invoiced_=1)
                self.validate(self.document(doctype, [row], True), None)
                saved = self.document(doctype, [self.expense(claimed=False)])
                candidate = self.document(doctype, deepcopy(saved.expenses))
                candidate.expenses[0].invoiced_ = 0
                self.validate(candidate, saved)

    def test_removing_unreferenced_rows_cannot_discard_server_provenance(self):
        for doctype in self.parents:
            for field in ('cargo_invoice_history', 'cargo_charge_key', 'cargo_tariff'):
                with self.subTest(doctype=doctype, field=field):
                    row = frappe._dict(name='expense-1', expense_type='cost-1')
                    row[field] = 'native-provenance'
                    saved = self.document(doctype, [row])
                    with self.assertRaises(frappe.ValidationError):
                        self.validate(self.document(doctype, []), saved)
            # Ordinary unreferenced manual rows have no protected history.
            saved = self.document(doctype, [frappe._dict(name='manual-row', expense_type='cost-1')])
            self.validate(self.document(doctype, []), saved)

    def test_foreign_child_identity_cannot_overwrite_another_parents_history(self):
        for doctype in self.parents:
            for new_parent in (False, True):
                with self.subTest(doctype=doctype, new_parent=new_parent):
                    # Omitting all provenance must not turn an existing foreign
                    # child into a new manual expense under this parent.
                    row = frappe._dict(name='another-parents-claimed-row', expense_type='cost-1')
                    with self.assertRaises(frappe.ValidationError):
                        self.validate(self.document(doctype, [row], new_parent),
                            self.document(doctype, []), existing_foreign_row=row.name)

    def test_native_claim_repeat_and_release_append_history_without_parent_bypass(self):
        import json
        from cargo_management.cargo_management.api.expense_billing import update_claim
        row = self.expense(claimed=False)
        writes = Mock(side_effect=lambda dt, name, values, **kwargs: row.update(values))
        with patch.object(frappe, 'db', SimpleNamespace(set_value=writes)), \
             patch.object(frappe, 'session', SimpleNamespace(user='authorized-accountant')), \
             patch.object(frappe.utils, 'now_datetime', return_value=datetime(2026, 11, 15)):
            update_claim(row, 'SI-1', 'claimed', 'SI-1')
            claimed = row.cargo_invoice_history
            update_claim(row, 'SI-1', 'claimed', 'SI-1')
            self.assertEqual(row.cargo_invoice_history, claimed)
            self.assertEqual(writes.call_count, 1)
            update_claim(row, 'SI-1', 'released_after_native_cancellation', None)
        self.assertIsNone(row.sales_invoice_no)
        self.assertEqual([event['action'] for event in json.loads(row.cargo_invoice_history)],
                         ['claimed', 'released_after_native_cancellation'])
        saved = self.document('FPLRoadJob', [row])
        self.validate(self.document(saved.doctype, deepcopy(saved.expenses)), saved)


class TestJobStatusTrainSelection(unittest.TestCase):
    """Filter contracts use document IDs and native access, never expense presence."""
    def setUp(self):
        from cargo_management.cargo_management.utils import reporting
        self.reporting = reporting
        def row(name, train=None, status='Completed', submission='Submitted'):
            jobs = [frappe._dict(doctype='FPLRailJob', train_number=train,
                job_name='Middle Mile', status='Completed')] if train else []
            return frappe._dict(FOname=name, BOName='BO-' + name, container_number=name,
                FO_status=status, booking_submission_status=submission, jobs=jobs)
        self.rows = {r.FOname: r for r in (row('FO-A', 'train-a'), row('FO-A2', 'train-a'),
            row('FO-B', 'train-b', submission='Cancelled'), row('FO-Draft', 'train-a', 'Draft', 'Draft'),
            row('FO-Unallocated'))}
        self.allowed_trains = {'train-a', 'train-b'}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.project = self.stack.enter_context(patch.object(reporting, 'projection', return_value=self.rows))
        self.stack.enter_context(patch.object(reporting, '_', side_effect=lambda text: text))
        self.stack.enter_context(patch.object(frappe, 'get_list', side_effect=self.get_list))
        def reject(message, *args, **kwargs):
            raise frappe.ValidationError(message)
        self.stack.enter_context(patch.object(frappe, 'throw', side_effect=reject))

    def get_list(self, doctype, **kwargs):
        if doctype == 'Container or Vehicle Request':
            return []
        self.assertEqual(doctype, 'FPL Perform Middle Mile')
        self.assertEqual(kwargs['pluck'], 'name')
        self.assertNotIn('ignore_permissions', kwargs)
        return sorted(set(kwargs['filters']['name'][1]) & self.allowed_trains)

    def report(self, **filters):
        return self.reporting.status(dict(company='company-a', transport_mode='Rail (Train)',
            check_train=1, **filters))

    def names(self, result):
        return {row['FOname'] for row in result[1]}

    def test_single_train_uses_rail_jobs_even_without_expenses(self):
        self.assertEqual(self.names(self.report(train_nos=['train-a'])), {'FO-A', 'FO-A2'})

    def test_multiple_trains_are_a_union_without_duplicate_freights(self):
        self.rows['FO-A'].jobs.append(deepcopy(self.rows['FO-A'].jobs[0]))
        result = self.report(train_nos=['train-a', 'train-b', 'train-a'])
        self.assertEqual(self.names(result), {'FO-A', 'FO-A2', 'FO-B'})
        self.assertEqual(len(result[1]), 3)

    def test_empty_nonexistent_and_unreadable_selections_are_empty(self):
        self.allowed_trains = {'train-a'}
        for selection in ([], None, ['missing'], ['train-b']):
            with self.subTest(selection=selection):
                self.assertEqual(self.report(train_nos=selection)[1], [])

    def test_json_list_is_accepted_and_malformed_shapes_rejected(self):
        self.assertEqual(self.names(self.report(train_nos='["train-a"]')), {'FO-A', 'FO-A2'})
        for value in ('not-json', '{}', '[1]', {'name': 'train-a'}, [''], [['train-a']], 1):
            with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
                self.report(train_nos=value)

    def test_hidden_booking_dates_do_not_filter_train_mode_or_mutate_input(self):
        filters = dict(company='company-a', customer='customer-a', transport_mode='Rail (Train)',
            check_train=1, train_nos=['train-a'], from_date='2099-01-01', to_date='2099-01-02')
        original = deepcopy(filters)
        self.reporting.status(filters)
        scope = self.project.call_args.args[0]
        self.assertEqual((scope['company'], scope['customer']), ('company-a', 'customer-a'))
        self.assertNotIn('from_date', scope)
        self.assertNotIn('to_date', scope)
        self.assertEqual(filters, original)

    def test_booking_precedence_and_road_and_overview_behavior_remain(self):
        for filters in (dict(company='company-a'),
                dict(transport_mode='Road (Truck)', check_train=1, train_nos=['train-a']),
                dict(transport_mode='Rail (Train)', check_train=1, check_booking=1,
                    train_nos=['train-a'], from_date='2026-11-01'),
                dict(transport_mode='Rail (Train)', check_train='0', train_nos=['train-a'])):
            with self.subTest(filters=filters):
                result = self.reporting.status(filters)
                self.assertEqual(self.names(result), set(self.rows))
                self.assertEqual(dict(self.project.call_args.args[0]), filters)
                self.assertIn('booking_submission_status', {c['fieldname'] for c in result[0]})


if __name__ == '__main__': unittest.main()
