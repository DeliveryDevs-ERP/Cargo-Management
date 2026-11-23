"""Native UOM/quantity regressions; no local Company or audit evidence required."""
import copy
import itertools
import uuid
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import patch
import frappe
from frappe.utils import add_days, nowdate
from cargo_management.cargo_management.doctype.booking_order.booking_order import BookingOrder, _get_cargo_billing_values
from cargo_management.tests.isolated_fixtures import RollbackCase
EXPLICIT = ('Per Container', 'Per Weight(Ton)', 'Per Bag')
GETTERS = ('get_sales_order_items', 'get_sales_invoice_items')

class TestBookingQuantity(RollbackCase):
    def insert(self, doctype, **values):
        return frappe.get_doc(dict(doctype=doctype, **values)).insert()

    def fixtures(self):
        if hasattr(self, 'customer'): return
        self.company=self.f.get('company1').name
        self.sales_person=self.f.get('sales-person').name
        self.customer=self.f.get('customer').name
        self.mode='Road (Truck)'
        from cargo_management.cargo_management.utils.configuration import resolve_service
        self.service=resolve_service('Long Haul',self.mode,self.company)
        self.start=self.f.get('location-1').name
        self.end=self.f.get('location-2').name
        self.patches.append(patch('frappe.defaults.get_user_default', side_effect=lambda key,*a,**kw: self.company if key.lower()=='company' else None))
        self.patches[-1].start()

    def row(self, rate_type, **values):
        result = dict(cargo_type='in-memory-item', size='20', avg_weight=19.25,
                      bag_qty=7, bag_weight=0.125, rate_type=rate_type,
                      rate=12.5, qty=3, amount=37.5)
        result.update(values)
        return result


    def unsaved_booking(self, rows):
        return frappe.get_doc(dict(doctype='Booking Order', transport_type='in-memory-road',
                                   bill_of_landing_number='test-bol', cargo_details=rows))


    def uom(self, name, whole=False):
        if not frappe.db.exists('UOM', name):
            self.insert('UOM', uom_name=name, must_be_whole_number=int(whole))
        return name


    def item(self, stock_uom, *, weight=None, alternate=None, factor=None, is_stock_item=False):
        self.fixtures()
        values = dict(item_code=self.uid + '-' + uuid.uuid4().hex[:5], item_group='Services',
                      stock_uom=stock_uom, is_stock_item=int(is_stock_item), is_sales_item=1)
        if weight is not None:
            values.update(weight_per_unit=weight, weight_uom='Kg')
        if alternate:
            values['uoms'] = [dict(uom=stock_uom, conversion_factor=1),
                              dict(uom=alternate, conversion_factor=factor)]
        return self.insert('Item', **values).name


    def booking(self, rate_type='Acre (US)', *, qty=2, bag_qty=7, weight=None,
                stock_uom=None, factor=None, amount=None, is_stock_item=False):
        self.fixtures()
        self.uom(rate_type)
        stock_uom = stock_uom or rate_type
        self.uom(stock_uom)
        item = self.item(stock_uom, weight=weight,
                         alternate=rate_type if factor is not None else None, factor=factor,
                         is_stock_item=is_stock_item)
        billed = bag_qty if rate_type == 'Per Bag' else qty * 19.25 if rate_type == 'Per Weight(Ton)' else qty
        values = dict(doctype='Booking Order', naming_series='BO-.YYYY.-', company=self.company,
                      customer=self.customer, bill_to=self.customer, sales_person=self.sales_person,
                      transport_type=self.mode, sales_order_type='Domestic', sales_order_date=nowdate(),
                      delivery_date=add_days(nowdate(), 1), long_haul_pickup_location=self.start,
                      long_haul_dropoff_location=self.end,
                      services=[dict(services=self.service, service_name='Long Haul', applicable=1)],
                      cargo_details=[self.row(rate_type, cargo_type=item, qty=qty, bag_qty=bag_qty,
                                             amount=billed * 12.5 if amount is None else amount, cargo_discrepancy_acknowledged=1)])
        return frappe.get_doc(values).insert()


    def sales_order(self, booking):
        names = frappe.get_all('Sales Order', filters={'custom_booking_order_id': booking.name}, pluck='name')
        self.assertEqual(len(names), 1)
        return frappe.get_doc('Sales Order', names[0])


    def test_legacy_branches_are_unchanged_in_both_getters(self):
        for rate_type in EXPLICIT:
            for getter in GETTERS:
                with self.subTest(rate_type=rate_type, getter=getter):
                    bo = self.unsaved_booking([self.row(rate_type, amount=123.45)])
                    before = copy.deepcopy(bo.as_dict())
                    result = getattr(bo, getter)()[0]
                    expected = (3, 19.25) if rate_type == 'Per Container' else (7, 0.125)
                    self.assertEqual((result['qty'], result['weight_per_unit']), expected)
                    self.assertEqual((result['rate'], result['amount'], result['uom']), (12.5, 123.45, rate_type))
                    self.assertEqual(bo.as_dict(), before)


    def test_all_enabled_ordinary_uoms_have_row_local_quantity(self):
        names = frappe.get_all('UOM', filters={'enabled': 1}, pluck='name')
        self.assertIn('Acre (US)', names)
        for name in names:
            if name in EXPLICIT:
                continue
            for getter in GETTERS:
                with self.subTest(uom=name, getter=getter):
                    result = getattr(self.unsaved_booking([self.row(name)]), getter)()[0]
                    self.assertEqual(result['qty'], 3)
                    self.assertNotIn('weight_per_unit', result)
                    self.assertEqual((result['rate'], result['amount']), (12.5, 37.5))


    def test_mixed_row_orders_never_inherit_quantity_or_weight(self):
        rows = [self.row('Per Container', qty=2, avg_weight=31),
                self.row('Per Bag', bag_qty=13, bag_weight=0.75),
                self.row('Acre (US)', qty=5, avg_weight=99)]
        for permutation in itertools.permutations(rows):
            for getter in GETTERS:
                with self.subTest(order=[r['rate_type'] for r in permutation], getter=getter):
                    values = getattr(self.unsaved_booking(list(permutation)), getter)()
                    for row, mapped in zip(permutation, values):
                        self.assertEqual(mapped['qty'], 13 if row['rate_type'] == 'Per Bag' else row['qty'])
                        if row['rate_type'] == 'Acre (US)':
                            self.assertNotIn('weight_per_unit', mapped)
                    values[0]['qty'] = -999
                    self.assertNotEqual(values[1]['qty'], -999)


    def test_owned_booking_mapping_is_read_only(self):
        bo = self.booking('Acre (US)', qty=2)
        before = copy.deepcopy(bo.as_dict())
        self.assertEqual(bo.docstatus, 0)
        self.assertEqual(bo.cargo_details[0].rate_type, 'Acre (US)')
        for getter in GETTERS:
            result = getattr(bo, getter)()[0]
            self.assertEqual(result['qty'], bo.cargo_details[0].qty)
            self.assertNotIn('weight_per_unit', result)
        self.assertEqual(bo.as_dict(), before)
        self.assertFalse(frappe.db.exists('Sales Order', {'custom_booking_order_id': bo.name}))


    def test_mapper_does_not_replace_empty_or_zero_quantities(self):
        for qty in (None, 0):
            for rate_type in ('Acre (US)', 'Per Container'):
                self.assertIs(_get_cargo_billing_values(frappe._dict(self.row(rate_type, qty=qty)))['qty'], qty)
            self.assertIs(_get_cargo_billing_values(frappe._dict(self.row('Per Bag', bag_qty=qty)))['qty'], qty)


    def test_domestic_road_acre_submission_creates_real_draft_sales_order_and_jobs(self):
        bo = self.booking(weight=2.75)
        bo.submit()
        bo.reload()
        so = self.sales_order(bo)
        self.assertEqual((bo.docstatus, so.docstatus), (1, 0))
        self.assertEqual((so.customer, so.company), (self.customer, self.company))
        row = so.items[0]
        self.assertEqual((row.uom, row.qty, row.rate, row.amount), ('Acre (US)', 2, 12.5, 25))
        self.assertEqual((row.conversion_factor, row.stock_qty, row.weight_per_unit), (1, 2, 2.75))
        self.assertEqual(so.custom_booking_order_id, bo.name)
        freight = frappe.get_all('FPL Freight Orders', filters={'sales_order_number': bo.name}, pluck='name')
        self.assertEqual(len(freight), 2)
        jobs = frappe.get_all('FPLRoadJob', filters={'sales_order_number': bo.name}, pluck='name')
        self.assertEqual(len(jobs), 2)
        for name in freight:
            fo = frappe.get_doc('FPL Freight Orders', name)
            self.assertEqual((fo.jobs[0].start_location, fo.jobs[0].end_location), (self.start, self.end))
            self.assertIn(fo.jobs[0].job_id, jobs)
        so.save()
        self.assertEqual(self.sales_order(bo).name, so.name)


    def test_new_explicit_rate_types_submit_with_version_one_quantities(self):
        for rate_type in EXPLICIT:
            bo = self.booking(rate_type, qty=1, bag_qty=4)
            bo.submit()
            so = self.sales_order(bo)
            expected_qty = 1 if rate_type == 'Per Container' else 19.25 if rate_type == 'Per Weight(Ton)' else 4
            expected_amount=float((Decimal('12.5')*Decimal(str(expected_qty))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
            self.assertEqual((so.docstatus, so.items[0].qty, so.items[0].amount), (0, expected_qty, expected_amount))
            self.assertEqual(so.items[0].weight_per_unit, 19.25 if rate_type == 'Per Container' else 0.125 if rate_type == 'Per Bag' else 0)


    def test_generic_item_without_weight_uses_native_defaults(self):
        bo = self.booking('Nos', qty=1)
        bo.submit()
        row = self.sales_order(bo).items[0]
        self.assertEqual((row.uom, row.qty, row.stock_qty, row.amount), ('Nos', 1, 1, 12.5))
        self.assertFalse(row.weight_per_unit)


    def test_native_item_conversion_and_stock_quantity(self):
        alternate = self.uom(self.uid + '-alternate')
        bo = self.booking(alternate, stock_uom='Nos', factor=3, weight=2.5)
        bo.submit()
        row = self.sales_order(bo).items[0]
        self.assertEqual((row.qty, row.rate, row.amount), (2, 12.5, 25))
        self.assertEqual((row.conversion_factor, row.stock_qty, row.weight_per_unit), (3, 6, 2.5))


    def test_generic_stock_item_submission(self):
        bo = self.booking('Acre (US)', qty=1, stock_uom='Nos', is_stock_item=True)
        bo.submit()
        row = self.sales_order(bo).items[0]
        self.assertEqual((row.qty, row.stock_qty, row.rate, row.amount), (1, 1, 12.5, 12.5))


    def test_native_uom_conversion_fallback_is_not_reimplemented(self):
        bo = self.booking('Acre (US)', stock_uom='Nos')
        bo.submit()
        row = self.sales_order(bo).items[0]
        self.assertEqual((row.qty, row.stock_qty, row.conversion_factor), (2, 2, 1))


    def test_native_amount_recalculation_does_not_modify_booking_amount(self):
        bo = self.booking(amount=999)
        bo.submit()
        so = self.sales_order(bo)
        bo.reload()
        self.assertEqual(so.items[0].amount, 25)
        self.assertEqual(bo.cargo_details[0].amount, 999)


    def test_missing_uom_and_missing_quantity_use_existing_validation(self):
        for missing in ('rate_type', 'qty'):
            bo = self.booking()
            bo.cargo_details[0].set(missing, None)
            with self.subTest(missing=missing), self.assertRaises(frappe.ValidationError):
                bo.submit()
            self.assertFalse(frappe.db.exists('Sales Order', {'custom_booking_order_id': bo.name}))


    def test_native_whole_number_validation_is_preserved(self):
        stock = self.uom(self.uid + '-whole', whole=True)
        alternate = self.uom(self.uid + '-fractional')
        bo = self.booking(alternate, qty=1, stock_uom=stock, factor=0.5)
        with self.assertRaises(frappe.ValidationError):
            bo.submit()


    def test_submission_failure_rolls_back_real_sales_order_and_children(self):
        bo = self.booking()
        frappe.db.savepoint('booking_qty_failure')
        with patch.object(BookingOrder, 'create_freight_orders', side_effect=frappe.ValidationError('test-only failure')):
            with self.assertRaises(frappe.ValidationError):
                bo.submit()
        # The Sales Order was inserted before the injected failure, uncommitted.
        self.assertTrue(frappe.db.exists('Sales Order', {'custom_booking_order_id': bo.name}))
        frappe.db.rollback(save_point='booking_qty_failure')
        self.assertFalse(frappe.db.exists('Sales Order', {'custom_booking_order_id': bo.name}))
        self.assertEqual(frappe.db.get_value('Booking Order', bo.name, 'docstatus'), 0)
        self.assertFalse(frappe.db.exists('FPL Freight Orders', {'sales_order_number': bo.name}))
