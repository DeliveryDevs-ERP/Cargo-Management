"""Native application regressions using only explicitly generated disposable fixtures."""
import json
import importlib
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import frappe
from cargo_management.tests.isolated_fixtures import (
    RollbackCase, make_booking, allocate_freight, complete_road,
    complete_until_rail, perform_rail, cross_case,
)

class TestNativeWorkflows(RollbackCase):
    def booking(self,**kwargs):
        return make_booking(self.f,self.uid+'-'+str(len(self.created)),**kwargs)


    def test_all_original_fields_and_approved_effective_layouts(self):
        root=Path(__file__).parents[1]
        source={json.loads(p.read_text())['name']:json.loads(p.read_text())['field_order'] for p in (root/'cargo_management/doctype').glob('*/*.json') if json.loads(p.read_text())['name'] in json.loads((root/'release_requirements.json').read_text())['original_doctypes']}
        self.assertEqual(len(source),31)
        for dt,names in source.items():
            fields=[f.fieldname for f in frappe.get_meta(dt).fields]
            self.assertTrue(set(names)<=set(fields),dt)
        for dt in ('Booking Order','FPL Freight Orders'):
            fields=[f.fieldname for f in frappe.get_meta(dt).fields]
            self.assertEqual([n for n in fields if n in source[dt]],source[dt],dt)
        fields=[f.fieldname for f in frappe.get_meta('FPL Perform Middle Mile').fields]
        self.assertEqual(fields.index('company'),fields.index('rail_number')+1)
        location=frappe.get_meta('Location').get_field('custom_location_type')
        self.assertEqual(location.fieldtype,'Select');self.assertFalse(location.reqd)
        self.assertTrue(location.allow_in_quick_entry)
        amount=frappe.get_meta('Expenses cdt').get_field('amount')
        self.assertEqual(amount.fieldtype,'Currency');self.assertFalse(amount.precision)
        self.assertEqual(frappe.db.sql("SHOW COLUMNS FROM `tabExpenses cdt` LIKE 'amount'")[0][1],'decimal(21,9)')


    def test_location_real_creation_grandfathering_and_invalid_values(self):
        from cargo_management.location import LOCATION_TYPES
        for kind in LOCATION_TYPES:
            doc=frappe.get_doc(dict(doctype='Location',location_name=self.uid+' '+kind,custom_location_type=kind)).insert()
            self.assertEqual(doc.custom_location_type,kind)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(dict(doctype='Location',location_name=self.uid+' missing')).insert()
        doc=frappe.get_doc(dict(doctype='Location',location_name=self.uid+' legacy',custom_location_type='Yard')).insert()
        frappe.db.set_value('Location',doc.name,'custom_location_type',None,update_modified=False)
        doc.reload();doc.area=1.25;doc.save();doc.reload()
        self.assertFalse(doc.custom_location_type)
        doc.custom_location_type='Yard';doc.save()
        doc.custom_location_type=''
        with self.assertRaises(frappe.ValidationError):doc.save()


    def test_effective_pnl_permissions_and_company_context(self):
        from frappe.desk.query_report import get_report_doc
        from cargo_management.cargo_management.utils.configuration import get_train_company_context
        reports=('Booking PNL','Customer PNL','Rail PNL Container Wise','RAIL PNL NEW','Road PNL Container Wise')
        users=frappe.get_all('User',filters={'enabled':1,'name':['like','%@example.invalid']},pluck='name')
        for user in users:
            frappe.set_user(user)
            roles=set(frappe.get_roles())
            for name in reports:
                authorized=bool(roles & {'Cargo Manager','Accounts Manager','System Manager'}) or (name in reports[:2] and 'Sales User' in roles)
                if authorized:self.assertTrue(get_report_doc(name))
                else:
                    with self.assertRaises(frappe.PermissionError):get_report_doc(name)
            if (frappe.has_permission('FPL Perform Middle Mile','read')
                    or frappe.has_permission('FPL Perform Middle Mile','create')):
                context=get_train_company_context()
                from cargo_management.permissions import allowed_companies
                allowed=allowed_companies(doctype='FPL Perform Middle Mile')
                if allowed is not None:self.assertTrue(set(context['companies'])<=allowed)
            else:
                with self.assertRaises(frappe.PermissionError):get_train_company_context()


    def test_new_train_company_authority_and_saved_ownership(self):
        from cargo_management.cargo_management.utils.configuration import get_train_company_context
        now=frappe.utils.now_datetime()
        train=frappe.get_doc(dict(doctype='FPL Perform Middle Mile',rail_number=self.uid,movement_type='Up',
            expected_departure_time_eda=now+timedelta(hours=1),expected_time_of_arrival_eta=now+timedelta(hours=2)))
        self.assertIsNone(get_train_company_context()['sole_company'])
        with self.assertRaises(frappe.ValidationError):train.insert()
        train.company=self.f.get('company1').name;train.insert()
        train.company=self.f.get('company2').name
        with self.assertRaisesRegex(frappe.ValidationError,'ownership'):train.save()


    def test_all_six_profiles_complete_with_native_jobs_and_draft_invoices(self):
        at=frappe.utils.now_datetime()-timedelta(hours=12)
        for mode in ('Road (Truck)','Rail (Train)'):
            for movement in ('Domestic','Import','Export'):
                with self.subTest(mode=mode,movement=movement):
                    key=self.uid+'-'+mode[:4]+'-'+movement
                    booking=make_booking(self.f,key,mode=mode,movement=movement,coherent_route=True,booking_date=frappe.utils.add_days(frappe.utils.nowdate(),-1))
                    freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
                    container=allocate_freight(self.f,freight,key)
                    if mode=='Rail (Train)':
                        complete_until_rail(self.f,freight,at)
                        train=perform_rail(self.f,booking,freight,container,key,at)
                        self.assertEqual(train.status,'Arrived')
                    for i,step in enumerate(list(freight.jobs)):
                        freight.reload();step=next(r for r in freight.jobs if r.name==step.name)
                        if step.status=='Completed':continue
                        moment=at+timedelta(hours=6,minutes=i*30)
                        if frappe.db.exists('FPLRoadJob',step.job_id):complete_road(self.f,frappe.get_doc('FPLRoadJob',step.job_id),moment)
                        elif frappe.db.exists('FPLYardJob',step.job_id):
                            job=frappe.get_doc('FPLYardJob',step.job_id)
                            job.set('gate_in' if job.job_name=='Gate In' else 'gate_out',moment);job.save()
                    freight.reload()
                    self.assertEqual(freight.status,'Completed')
                    self.assertTrue(all(r.status=='Completed' for r in freight.jobs))
                    invoice=frappe.get_doc('Sales Invoice',booking.create_and_submit_sales_invoice())
                    self.assertEqual((invoice.docstatus,invoice.grand_total),(0,100))


    def test_precision_expense_purchase_and_extra_invoice_mapping(self):
        booking=self.booking(selected_labels=['Long Haul'])
        freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
        job=frappe.get_doc('FPLRoadJob',{'freight_order_id':freight.name})
        row=job.append('expenses',dict(expense_type=self.f.get('financial-ui-cost').name,
            client=self.f.get('supplier').name,amount=1.25,invoiced_=1))
        job.save();purchase=row.purchase_invoice_no;rowname=row.name;job.reload()
        row=next(r for r in job.expenses if r.name==rowname)
        self.assertEqual(row.amount,1.25)
        self.assertEqual(frappe.get_doc('Purchase Invoice',purchase).grand_total,1.25)
        base=booking.create_and_submit_sales_invoice()
        from cargo_management.cargo_management.api.expense_billing import fetch_expenses_items
        values=fetch_expenses_items(base)
        self.assertEqual(len(values['expenses']),1)
        self.assertEqual(values['expenses'][0]['rate'],1.25)
        before=[r.purchase_invoice_no for r in job.expenses]
        job.save();job.reload()
        self.assertEqual([r.purchase_invoice_no for r in job.expenses],before)


    def test_native_container_bag_ton_generic_and_override_roundtrip(self):
        for basis,kwargs,quantity,total in [('Per Container',dict(qty=2),2,200),
                ('Per Bag',dict(qty=2,bag_qty=100),100,10000),
                ('Per Weight(Ton)',dict(qty=2,avg_weight=20),40,4000),('Nos',dict(qty=2),2,200)]:
            booking=self.booking(rate_type=basis,**kwargs)
            order=frappe.get_doc('Sales Order',{'custom_booking_order_id':booking.name})
            self.assertEqual((order.items[0].qty,order.grand_total),(quantity,total))
            freights=frappe.get_all('FPL Freight Orders',filters={'sales_order_number':booking.name},fields=['cargo_contracted_revenue','bag_qty'])
            self.assertEqual(sum(r.cargo_contracted_revenue for r in freights),total)
            if basis=='Per Bag':self.assertEqual(sum(r.bag_qty for r in freights),100)
        booking=self.booking(submit=False,qty=2)
        row=booking.cargo_details[0]
        row.cargo_billing_override=1;row.cargo_override_reason='Explicit transaction-local QA override'
        row.cargo_override_amount=300;row.amount=300;booking.save();booking.reload()
        old_hash=booking.cargo_details[0].cargo_billing_input_hash
        booking.bill_of_landing_number=self.uid+' unrelated';booking.save();booking.reload()
        self.assertEqual(booking.cargo_details[0].cargo_billing_input_hash,old_hash)
        self.assertEqual(booking.cargo_details[0].cargo_native_amount,300)


    def test_manual_acknowledgement_and_recorded_billing_version_guard(self):
        booking=self.booking(qty=2,rate=70,amount=280,submit=False)
        booking.cargo_details[0].cargo_discrepancy_acknowledged=1
        booking.save();booking.submit()
        order=frappe.get_doc('Sales Order',{'custom_booking_order_id':booking.name})
        self.assertEqual(order.grand_total,140)
        self.assertEqual(booking.cargo_details[0].amount,280)
        draft=self.booking(submit=False)
        draft.cargo_billing_version=0
        with self.assertRaisesRegex(frappe.ValidationError,'contract version'):draft.save()


    def test_native_booking_cancellation_amendment_and_route_copy(self):
        booking=self.booking(selected_labels=[])
        original_route=booking.fm_pickup_location
        self.assertNotEqual(original_route,booking.pickup_location)
        booking.cancel()
        amended=frappe.copy_doc(booking);amended.docstatus=0;amended.amended_from=booking.name
        amended.insert();amended.submit()
        self.assertEqual(amended.amended_from,booking.name)
        self.assertEqual(amended.fm_pickup_location,original_route)
        self.assertEqual(amended.cargo_billing_version,1)


    def test_optimistic_concurrency_rejects_stale_save(self):
        booking=self.booking(selected_labels=['Long Haul'])
        freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
        first=frappe.get_doc('FPLRoadJob',freight.jobs[0].job_id)
        stale=frappe.get_doc(first.doctype,first.name)
        first.vehicle_number=self.uid+' first';first.save()
        stale.vehicle_number=self.uid+' stale'
        with self.assertRaises(frappe.TimestampMismatchError):stale.save()


    def test_cross_stuff_injected_failure_rolls_back_every_transferred_identity(self):
        booking,source,target,performance=cross_case(self.f,self.uid,existing=True,submit=False)
        keys=[(d.doctype,d.name) for d in (source,target,performance)]
        before={key:frappe.as_json(frappe.get_doc(*key).as_dict()) for key in keys}
        journals=frappe.db.count('Cargo Cross Stuff Transfer')
        frappe.db.savepoint('rmd_cross_failure')
        with patch.object(type(performance),'amend_CFOs',side_effect=frappe.ValidationError('RMD injected cross failure')):
            with self.assertRaisesRegex(frappe.ValidationError,'RMD injected'):performance.submit()
        frappe.db.rollback(save_point='rmd_cross_failure')
        self.assertEqual({key:frappe.as_json(frappe.get_doc(*key).as_dict()) for key in keys},before)
        self.assertEqual(frappe.db.count('Cargo Cross Stuff Transfer'),journals)


    def test_cross_stuff_journal_retains_cost_history_and_blocks_unsafe_reversal(self):
        booking,source,target,performance=cross_case(self.f,self.uid,existing=True,submit=True)
        journal=frappe.get_doc('Cargo Cross Stuff Transfer',{'performance':performance.name})
        self.assertTrue(journal.mappings)
        retired=[r for r in journal.mappings if r.disposition=='Retained financial history']
        self.assertTrue(retired)
        for mapping in retired:self.assertEqual(frappe.db.get_value(mapping.job_type,mapping.job,'cargo_retired'),1)
        with self.assertRaises(frappe.ValidationError):performance.cancel()


    def test_all_reports_and_print_formats_without_posting(self):
        req=json.loads((Path(__file__).parents[1]/'release_requirements.json').read_text())
        from cargo_management.cargo_management.utils.reporting import execute_report
        for name in req['reports']:
            result=execute_report(name,{'company':self.f.get('company1').name})
            self.assertIsInstance(result[0],list,name)
            empty=execute_report(name,{'company':self.f.get('company2').name,'from_date':'2000-01-01','to_date':'2000-01-02'})
            self.assertIsInstance(empty[0],list,name)
        booking=self.booking();invoice=booking.create_and_submit_sales_invoice()
        for name in req['print_formats']:
            html=frappe.get_print('Sales Invoice',invoice,print_format=name,no_letterhead=1)
            self.assertIn('cargo-invoice',html)
            if 'qr' in name.lower():self.assertIn('data:image/png;base64,',html)


    def test_rail_query_apis_and_cost_free_operational_rewinds(self):
        from cargo_management.cargo_management.doctype.fpl_perform_middle_mile import query
        from cargo_management.cargo_management.doctype.fpl_perform_middle_mile.fpl_perform_middle_mile import (
            cancel_loading,cancel_departure,validate_weight_Loading,
        )
        at=frappe.utils.now_datetime()-timedelta(hours=12)
        # A genuinely cost-free configuration is represented only inside this
        # test process; no existing Cost Type or business record is changed.
        with patch('cargo_management.expense_controls.initialize_fixed_costs',return_value=None):
            booking=self.booking(mode='Rail (Train)',movement='Import',coherent_route=True)
            freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
            container=allocate_freight(self.f,freight,self.uid)
            complete_until_rail(self.f,freight,at)
            args=dict(doctype='FPL Containers',txt=container.name,searchfield='name',start=0,page_len=20,
                filters={'container_location':booking.mm_loading_station,'container_next_location':booking.mm_offloading_station})
            self.assertIn(container.name,{r[0] for r in query.get_applicable_jobs(**args)})
            train=perform_rail(self.f,booking,freight,container,self.uid,at,stop_at='Loaded')
            loading=args|{'filters':{'parent':train.name}}
            self.assertIn(container.name,{r[0] for r in query.get_containers_from_Loading(**loading)})
            self.assertTrue(query.get_wagons_from_train(train.name))
            self.assertTrue(query.fetch_wagons_from_undeparted_trains(booking.mm_loading_station,'Up'))
            self.assertTrue(validate_weight_Loading(train.name))
            cancel_loading(train.name);train.reload();self.assertEqual(train.status,'Train Formed')
            train.loading_time=at+timedelta(hours=1);train.loading_end_time=at+timedelta(hours=2)
            train.finish_loading=1;train.status='Loaded';train.save()
            for row in train.middle_mile_in_loading:
                if row.container:row.departed_=1
            train.finish_departure=1;train.departure_time=at+timedelta(hours=2,minutes=5);train.status='Departed';train.save()
            cancel_departure(train.name);train.reload();self.assertEqual(train.status,'Loaded')
            frappe.set_user(self.f.get('user-denied').name)
            for call in (lambda:query.get_applicable_jobs(**args),lambda:query.get_containers_from_Loading(**loading),
                    lambda:query.get_wagons_from_train(train.name),lambda:validate_weight_Loading(train.name),
                    lambda:cancel_loading(train.name),lambda:cancel_departure(train.name)):
                with self.assertRaises(frappe.PermissionError):call()


    def test_cross_stuff_query_entrypoints_exact_ids_and_pagination(self):
        from cargo_management.cargo_management.doctype.perform_cross_stuff import query
        booking,source,target,performance=cross_case(self.f,self.uid,existing=True,submit=False)
        source_container=frappe.db.get_value('FPL Containers',{'freight_order_id':source.name},'name')
        target_container=frappe.db.get_value('FPL Containers',{'freight_order_id':target.name},'name')
        args=dict(doctype='FPL Containers',txt='',searchfield='name',start=0,page_len=20,filters={'booking_order_id':booking.name})
        self.assertIn(source_container,{r[0] for r in query.get_FO_containers(**args)})
        self.assertIn(target_container,{r[0] for r in query.get_CFO_containers(**args)})
        self.assertTrue(query.get_unique_service_types(**args))
        self.assertTrue(query.get_BOs_name(**(args|{'txt':booking.name})))
        included=args|{'filters':{'in_container':[source_container,target_container]}}
        self.assertEqual({r[0] for r in query.get_Containers_for_CS_expenses(**included)},{source_container,target_container})
        self.assertEqual(len(query.get_Containers_for_CS_expenses(**(included|{'page_len':1}))),1)
        self.assertEqual(len(query.get_Containers_for_CS_expenses(**(included|{'page_len':0}))),2)
        frappe.set_user(self.f.get('user-denied').name)
        for call in (lambda:query.get_FO_containers(**args),lambda:query.get_CFO_containers(**args),
                lambda:query.get_unique_service_types(**args),lambda:query.get_BOs_name(**args),
                lambda:query.get_Containers_for_CS_expenses(**included)):
            with self.assertRaises(frappe.PermissionError):call()


    def test_live_tariff_prices_fixed_costs_idempotence_and_partial_receipt(self):
        from cargo_management.cargo_management.utils.rail_charges import append_train_charges
        expected={'variable_amounts':[150,175], 'total_amount':345}
        train=self.charge_candidate()
        append_train_charges(train)
        variable=[r for r in train.expenses if r.cargo_tariff]
        self.assertEqual(sorted(r.amount for r in variable),sorted(expected['variable_amounts']))
        self.assertEqual(sum(r.amount for r in train.expenses),expected['total_amount'])
        self.assertEqual(len({r.cargo_charge_key for r in train.expenses}),len(train.expenses))
        prior=[r.as_dict() for r in train.expenses]
        append_train_charges(train)
        self.assertEqual([r.as_dict() for r in train.expenses],prior)
        train.set('expenses',[]);train.middle_mile_copy[1].received_=0
        append_train_charges(train)
        self.assertTrue(train.expenses)
        self.assertTrue(all(r.container_number==train.middle_mile_copy[0].container for r in train.expenses))


    def test_live_tariff_missing_supplier_missing_match_and_history_guard(self):
        from cargo_management.cargo_management.utils.rail_charges import append_train_charges
        from cargo_management.cargo_management.utils import configuration
        train=self.charge_candidate()
        with patch('cargo_management.cargo_management.utils.getSupplierForCostType.get_supplier',return_value=None):
            with self.assertRaisesRegex(frappe.ValidationError,'Supplier'):append_train_charges(train)
        self.assertFalse(train.expenses)
        catalog=configuration.catalog
        with patch.object(configuration,'catalog',side_effect=lambda dt,*a,**k:[] if dt=='Rail Freight Cost' else catalog(dt,*a,**k)):
            with self.assertRaisesRegex(frappe.ValidationError,'No rail tariff'):append_train_charges(train)
        self.assertFalse(train.expenses)
        append_train_charges(train)
        train.middle_mile_in_loading[0].weight='20';train.middle_mile_in_loading[1].weight='30'
        with self.assertRaisesRegex(frappe.ValidationError,'historical expenses'):append_train_charges(train)


    def test_unreceived_container_prevents_wagon_reassignment(self):
        at=frappe.utils.now_datetime()-timedelta(hours=12)
        bookings=[];freights=[];containers=[]
        for index,size in enumerate((20,40)):
            booking=make_booking(self.f,self.uid+str(index),mode='Rail (Train)',size=size,avg_weight=25,
                coherent_route=True,booking_date=frappe.utils.add_days(frappe.utils.nowdate(),-1))
            freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
            container=allocate_freight(self.f,freight,self.uid+str(index));complete_until_rail(self.f,freight,at)
            bookings.append(booking);freights.append(freight);containers.append(container)
        train=perform_rail(self.f,bookings[0],freights[0],containers[0],self.uid,at,stop_at='Departed',additional_containers=containers[1:])
        for row in train.middle_mile_copy:row.received_=int(row.container==containers[0].name)
        train.finish_arrival=1;train.actual_arrival_datetime=at+timedelta(hours=3);train.status='Arrived';train.save()
        wagon=frappe.get_doc('Wagons',train.wagons[0].wagon_number)
        candidate=frappe.get_doc(dict(doctype=train.doctype,rail_number=self.uid+'-Reuse',company=train.company,
            movement_type='Up',status='Train Formed',finish_train_formation=1,departure_location=train.departure_location,
            arrival_location=train.arrival_location,expected_departure_time_eda=at+timedelta(hours=5),
            expected_time_of_arrival_eta=at+timedelta(hours=7),wagons=[dict(wagon_number=wagon.name,wagon_type=wagon.type)]))
        with self.assertRaisesRegex(frappe.ValidationError,'unreceived'):candidate.insert()
        self.assertEqual(frappe.db.get_value('Wagons',wagon.name,'train_no'),train.name)


    def test_print_description_decodes_entities_and_escapes_untrusted_markup(self):
        from cargo_management.print_context import get_cargo_print_context
        from jinja2 import Environment
        invoice=frappe.get_doc({'doctype':'Sales Invoice','items':[{'description':'Cargo &amp; &lt;layout&gt; <b>bold</b> &lt;img src=x onerror=alert(1)&gt;'}]})
        context=get_cargo_print_context(invoice)
        text=context['items'][0]['description']
        self.assertEqual(text,'Cargo & <layout> bold <img src=x onerror=alert(1)>')
        rendered=Environment().from_string('{{ text|e }}').render(text=text)
        self.assertIn('Cargo &amp; &lt;layout&gt;',rendered)
        self.assertNotIn('&amp;amp;',rendered)
        self.assertNotIn('<img',rendered)


    def test_native_sales_order_invoice_mapping_binds_only_new_verified_cargo_drafts(self):
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
        from cargo_management.cargo_management.api.expense_billing import validate_cargo_invoice
        booking=make_booking(self.f,self.uid,selected_labels=['Long Haul'],qty=2,rate=12.5)
        order=frappe.get_doc('Sales Order',{'custom_booking_order_id':booking.name});order.submit()
        invoice=make_sales_invoice(order.name)
        self.assertFalse(invoice.custom_booking_order)
        validate_cargo_invoice(invoice)
        self.assertEqual(invoice.custom_booking_order,booking.name)
        invoice.insert()
        self.assertEqual((invoice.docstatus,invoice.grand_total),(0,25))
        self.assertTrue(all(r.sales_order==order.name for r in invoice.items))
        # Existing blank historical references are deliberately not backfilled.
        invoice.custom_booking_order=None;invoice.save();invoice.reload()
        self.assertFalse(invoice.custom_booking_order)
        ordinary=frappe.get_doc({'doctype':'Sales Invoice','items':[{'sales_order':None}]})
        validate_cargo_invoice(ordinary);self.assertFalse(ordinary.custom_booking_order)
        other=make_booking(self.f,self.uid+'-other',selected_labels=['Long Haul'])
        other_order=frappe.get_doc('Sales Order',{'custom_booking_order_id':other.name})
        mixed=make_sales_invoice(order.name);mixed.append('items',{'sales_order':other_order.name})
        with self.assertRaisesRegex(frappe.ValidationError,'unambiguous'):validate_cargo_invoice(mixed)
        wrong=make_sales_invoice(order.name);wrong.company=self.f.get('company2').name
        with self.assertRaises(frappe.ValidationError):validate_cargo_invoice(wrong)
        forged=make_sales_invoice(order.name);forged.custom_booking_order=other.name
        with self.assertRaises(frappe.ValidationError):validate_cargo_invoice(forged)
        denied=make_sales_invoice(order.name);frappe.set_user(self.f.get('user-denied').name)
        with self.assertRaises(frappe.PermissionError):validate_cargo_invoice(denied)


    def test_invoice_description_uses_route_when_legacy_flat_location_fields_are_empty(self):
        booking=make_booking(self.f,self.uid,selected_labels=['Long Haul'],submit=False)
        booking.pickup_location=None;booking.dropoff_location=None
        description=booking.get_sales_invoice_items()[0]['description']
        self.assertIn(self.f.get('location-1').name,description)
        self.assertIn(self.f.get('location-2').name,description)
        self.assertNotIn('None',description)
        booking.bill_of_landing_number=None
        self.assertNotIn('None',booking.get_sales_invoice_items()[0]['description'])


    def test_request_allocation_validation_and_native_cancel_amend_lineage(self):
        booking=make_booking(self.f,self.uid,selected_labels=['Long Haul'])
        def request(rows):
            return frappe.get_doc(dict(doctype='Container or Vehicle Request',booking_order_id=booking.name,
                yard_location=self.f.get('location-1').name,cargo_type='Non Containerised',table_ktch=rows))
        values=dict(qty=1,size='40',type=self.f.get('container-type-40').name,pickup_location=self.f.get('location-2').name)
        for invalid in [values|{'qty':-1},values|{'qty':0},values|{'size':'20'}]:
            with self.assertRaises(frappe.ValidationError):request([invalid]).insert()
        empty=request([]).insert();empty.submit();empty.cancel()
        self.assertEqual(empty.docstatus,2)
        amended=frappe.copy_doc(empty);amended.docstatus=0;amended.amended_from=empty.name
        amended.set('table_ktch',[values]);amended.insert();amended.submit()
        freights=frappe.get_all('FPL Freight Orders',filters={'cargo_request':amended.name},pluck='name')
        self.assertEqual(len(freights),1)
        with self.assertRaisesRegex(frappe.ValidationError,'Receiving work exists'):amended.cancel()
        self.assertEqual(frappe.db.get_value(amended.doctype,amended.name,'docstatus'),1)
        self.assertEqual(freights,frappe.get_all('FPL Freight Orders',filters={'cargo_request':amended.name},pluck='name'))


    def test_sales_only_booking_submit_retains_costs_for_native_accounting_authority(self):
        frappe.set_user(self.f.get('user-sales-only').name)
        self.assertFalse(frappe.has_permission('Purchase Invoice','create'))
        booking=make_booking(self.f,self.uid,selected_labels=['Long Haul'])
        self.assertEqual(booking.docstatus,1)
        freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
        job=frappe.get_doc('FPLRoadJob',freight.jobs[0].job_id)
        self.assertTrue(job.expenses)
        self.assertTrue(all(not row.purchase_invoice_no for row in job.expenses))
        with self.assertRaises(frappe.PermissionError):job.create_pending_purchase_invoices()
        frappe.set_user(self.f.get('user-accounting').name)
        created=job.create_pending_purchase_invoices()
        self.assertEqual(len(created),len(job.expenses))
        self.assertEqual(job.create_pending_purchase_invoices(),[])
        self.assertTrue(all(frappe.db.get_value('Purchase Invoice',name,'docstatus')==0 for name in created))


    def test_freight_job_references_and_booking_identity_cannot_be_forged(self):
        one=make_booking(self.f,self.uid+'-one',selected_labels=['Long Haul'])
        two=make_booking(self.f,self.uid+'-two',selected_labels=['Long Haul'])
        source=frappe.get_doc('FPL Freight Orders',{'sales_order_number':one.name})
        other=frappe.get_doc('FPL Freight Orders',{'sales_order_number':two.name})
        source.jobs[0].job_id=other.jobs[0].job_id
        with self.assertRaisesRegex(frappe.ValidationError,'another Freight Order'):source.save()
        source.reload();source.sales_order_number=two.name
        with self.assertRaisesRegex(frappe.ValidationError,'cannot be reassigned'):source.save()


    def test_native_document_hooks_reject_forged_http_payloads(self):
        from cargo_management.cargo_management.api.expense_billing import update_expense_references
        from cargo_management.cargo_management.doctype.booking_order.booking_order import check_booking_order_status
        for payload in ({'doctype':'Sales Invoice','docstatus':1},'{}',None):
            for fn in (update_expense_references,check_booking_order_status):
                with self.assertRaises(frappe.PermissionError):fn(payload,'on_submit')


    def test_double_twenty_link_query_and_repeated_performance_sync_do_not_clone_costs(self):
        from cargo_management.cargo_management.doctype.fplroadjob.query import get_applicable_containers
        from cargo_management.cargo_management.doctype.fplroadjob.fplroadjob import link_container,sync_with_linked_job
        booking=make_booking(self.f,self.uid,qty=2,size=20,selected_labels=['Long Haul'])
        names=frappe.get_all('FPL Freight Orders',filters={'sales_order_number':booking.name},pluck='name',order_by='name')
        freights=[frappe.get_doc('FPL Freight Orders',name) for name in names]
        containers=[allocate_freight(self.f,doc,self.uid+str(index)) for index,doc in enumerate(freights)]
        jobs=[frappe.get_doc('FPLRoadJob',doc.jobs[0].job_id) for doc in freights]
        for container,job in zip(containers,jobs):
            frappe.db.set_value('FPL Containers',container.name,'container_location',job.job_start_location)
        args=dict(doctype='FPL Containers',txt='',searchfield='name',start=0,page_len=20,
                  filters={'job_start_location':jobs[0].job_start_location})
        eligible=get_applicable_containers(**args)
        self.assertTrue({doc.name for doc in containers}<={row[0] for row in eligible})
        link_container(containers[1].name,freights[0].container_number,jobs[0].job_type,freights[0].name)
        job=jobs[0]
        job.container_number_to_link=containers[1].name
        job.vehicle_number=self.uid
        job.vehicle_supplier=self.f.get('supplier').name
        job.save()
        before=frappe.db.count('Expenses cdt',{'parent':jobs[1].name})
        sync_with_linked_job(job.name);sync_with_linked_job(job.name)
        jobs[1].reload()
        self.assertEqual(jobs[1].vehicle_number,self.uid)
        self.assertEqual(len(jobs[1].expenses),before)
        frappe.set_user(self.f.get('user-denied').name)
        for operation in [lambda:link_container(containers[1].name,freights[0].container_number,jobs[0].job_type,freights[0].name),
                          lambda:sync_with_linked_job(job.name)]:
            with self.assertRaises(frappe.PermissionError):operation()


    def test_extra_invoice_typed_scope_forgery_and_draft_reservation(self):
        from cargo_management.cargo_management.api.expense_billing import fetch_expenses_items, source_rows
        booking = make_booking(self.f, self.uid, selected_labels=['Long Haul'])
        freight = frappe.get_doc('FPL Freight Orders', {'sales_order_number': booking.name})
        job = frappe.get_doc('FPLRoadJob', freight.jobs[0].job_id)
        expense = job.expenses[0]
        expense.invoiced_ = 1
        job.save()
        base_name = booking.create_and_submit_sales_invoice()
        result = fetch_expenses_items(base_name)
        self.assertEqual(len(result['expenses']), 1)
        base = frappe.get_doc('Sales Invoice', base_name)
        extra = frappe.copy_doc(base)
        extra.is_debit_note = 1
        extra.return_against = base.name
        extra.set('items', result['expenses'])
        extra.insert()
        self.assertEqual(extra.docstatus, 0)
        self.assertEqual(len(source_rows(extra)), 1)
        self.assertEqual(fetch_expenses_items(base_name)['expenses'], [])
        self.assertFalse(frappe.db.get_value('Expenses cdt', expense.name, 'sales_invoice_no'))
        with self.assertRaisesRegex(frappe.ValidationError, 'submitted base'):
            source_rows(extra, require_submitted_base=True)
        duplicate = frappe.copy_doc(extra)
        with self.assertRaisesRegex(frappe.ValidationError, 'reserved'):
            duplicate.insert()
        item = extra.items[0]
        item.custom_cargo_expense_parent = self.f.get('booking-Road-Domestic').name
        with self.assertRaises((frappe.DoesNotExistError, frappe.ValidationError)):
            source_rows(extra)


    def test_different_booking_cannot_supply_expense_or_invoice_context(self):
        from cargo_management.cargo_management.api.expense_billing import expense_context, invoice_context
        booking = make_booking(self.f, self.uid, selected_labels=['Long Haul'])
        freight = frappe.get_doc('FPL Freight Orders', {'sales_order_number': booking.name})
        allocation = allocate_freight(self.f, freight, self.uid)
        original = self.f.get('booking-Road-Domestic')
        other = frappe.get_doc('FPL Freight Orders', {'sales_order_number': original.name})
        job = frappe.get_doc('FPLRoadJob', other.jobs[0].job_id)
        row = job.expenses[0]
        row.container_number = allocation.name
        with self.assertRaisesRegex(frappe.ValidationError, 'another Booking'):
            expense_context(job, row)
        invoice = frappe.get_doc('Sales Invoice', booking.create_and_submit_sales_invoice())
        invoice.company = self.f.get('company2').name
        with self.assertRaisesRegex(frappe.ValidationError, 'Company'):
            invoice_context(invoice)


    def test_job_generation_identity_change_and_original_hook_endpoints(self):
        prefix = 'cargo_management.cargo_management.doctype.'
        mod = importlib.import_module(prefix+'fpl_freight_orders.fpl_freight_orders')
        bo_mod = importlib.import_module(prefix+'booking_order.booking_order')
        booking = make_booking(self.f, self.uid, qty=2, selected_labels=['Long Haul'])
        source = frappe.get_doc('FPL Freight Orders', {'sales_order_number':booking.name})
        container = allocate_freight(self.f, source, self.uid)
        count = frappe.db.count('FPLRoadJob', {'freight_order_id':source.name})
        source.process_jobs(); mod.create_Job_withoutId(source.name)
        self.assertEqual(frappe.db.count('FPLRoadJob', {'freight_order_id':source.name}), count)
        mod.change_container_number(source.name, 'DEMO9999998')
        container.reload(); source.reload()
        self.assertEqual(container.container_number, 'DEMO9999998')
        self.assertTrue(all(frappe.db.get_value('FPLRoadJob',row.job_id,'container_number')=='DEMO9999998' for row in source.jobs))
        self.assertEqual(bo_mod.get_sales_person(booking.customer), self.f.get('sales-person').name)
        order = frappe.get_doc('Sales Order', {'custom_booking_order_id':booking.name})
        with self.assertRaises(frappe.ValidationError):
            bo_mod.check_booking_order_status(order, 'on_trash')
        from cargo_management.cargo_management.api.Sales_inv_validation_overload import update_expense_references
        update_expense_references(frappe.get_doc('Sales Invoice', booking.create_and_submit_sales_invoice()), 'on_submit')
        # All mutating paths deny a non-operator before changing records.
        frappe.set_user(self.f.get('user-denied').name)
        for operation in [lambda:source.process_jobs(),lambda:mod.create_Job_withoutId(source.name),
            lambda:mod.change_container_number(source.name,'DEMO9999997'),lambda:bo_mod.get_sales_person(booking.customer),
            lambda:bo_mod.check_booking_order_status(order,'on_trash')]:
            with self.assertRaises(frappe.PermissionError):operation()


    def test_active_deferred_item_blocks_without_rewriting_its_flags(self):
        item=self.f.get('item-1')
        frappe.db.set_value('Item',item.name,'enable_deferred_revenue',1)
        with self.assertRaisesRegex(frappe.ValidationError,'inactive deferred'):
            make_booking(self.f,self.uid,submit=False)
        self.assertEqual(frappe.db.get_value('Item',item.name,'enable_deferred_revenue'),1)


    def charge_candidate(self,weights=(25,25),received=(1,1)):
        at=frappe.utils.now_datetime()-timedelta(hours=12)
        bookings=[];containers=[]
        for i,(size,weight) in enumerate(zip((20,40),weights)):
            booking=make_booking(self.f,self.uid+'-'+str(i),mode='Rail (Train)',movement='Import',size=size,
                avg_weight=weight,coherent_route=True,booking_date=frappe.utils.add_days(frappe.utils.nowdate(),-1))
            freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
            container=allocate_freight(self.f,freight,self.uid+str(i))
            bookings.append(booking);containers.append((container,freight))
        train=frappe.get_doc(dict(doctype='FPL Perform Middle Mile',name=self.uid+'-Candidate',__islocal=1,
            company=bookings[0].company,movement_type='Up',departure_location=bookings[0].mm_loading_station,
            arrival_location=bookings[0].mm_offloading_station,
            wagons=[dict(wagon_number=self.uid+'-new-unsaved-wagon',wagon_type=self.f.get('reference-wagon-BFC').name)]))
        for i,(container,freight) in enumerate(containers):
            row=dict(container=container.name,fo=freight.name,wagon_number=train.wagons[0].wagon_number,
                size=str(freight.size),weight=str(freight.weight))
            train.append('middle_mile_in_loading',row)
            train.append('middle_mile_copy',dict(**row,received_=received[i]))
        return train


    def test_more_than_twenty_freight_orders_cancel_without_leftovers(self):
        booking=self.booking(qty=21,selected_labels=[])
        order=frappe.db.get_value('Sales Order',{'custom_booking_order_id':booking.name},'name')
        self.assertEqual(frappe.db.count('FPL Freight Orders',{'sales_order_number':booking.name}),21)
        booking.cancel()
        self.assertEqual(frappe.db.count('FPL Freight Orders',{'sales_order_number':booking.name}),0)
        self.assertFalse(frappe.db.exists('Sales Order',order))
