"""Explicit synthetic test setup; never imported by installation hooks.

All writers require a disposable site/database pair and a matching run marker.
Nothing reads a development database, commercial evidence or an external service.
"""
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import uuid

import frappe
from frappe.utils import add_days, nowdate


def require_disposable():
    run = str(frappe.conf.get('cargo_publication_test_run') or '')
    if not re.fullmatch('[a-f0-9]{16}', run):
        raise RuntimeError('Explicit disposable test run marker is required')
    expected_site = 'cargo-publication-' + run + '.localhost'
    expected_db = 'cargo_publication_' + run
    if frappe.local.site != expected_site or frappe.conf.get('db_name') != expected_db:
        raise RuntimeError('Tests refuse primary, aliases and unowned site/database pairs')
    if frappe.db.sql('SELECT DATABASE()')[0][0] != expected_db:
        raise RuntimeError('Connected database does not match the disposable owner')
    if frappe.conf.get('cargo_crypto_enabled') or not frappe.conf.get('mute_emails'):
        raise RuntimeError('Disposable tests require crypto off and muted email')
    return run


def directory():
    require_disposable()
    path = Path(frappe.get_site_path('private', 'cargo-publication'))
    path.mkdir(parents=True, exist_ok=True)
    return path


class Fixtures:
    def __init__(self, empty=False):
        self.run = require_disposable()
        self.directory = directory()
        self.path = self.directory / 'synthetic-fixtures.json'
        self.label = 'Synthetic Cargo ' + self.run[:8]
        self.data = dict(run=self.run, records={}) if empty else json.loads(self.path.read_text())
        if self.data['run'] != self.run:
            raise RuntimeError('Synthetic fixtures belong to another disposable run')

    def create(self, key, doctype, **values):
        if key in self.data['records']:
            row = self.data['records'][key]
            if row['doctype'] != doctype or not frappe.db.exists(doctype, row['name']):
                raise RuntimeError('Missing or incompatible synthetic fixture: ' + key)
            return frappe.get_doc(doctype, row['name'])
        name = values.pop('set_name', None)
        if name and frappe.db.exists(doctype, name):
            raise RuntimeError('Refusing to adopt an unowned record: ' + key)
        doc = frappe.get_doc(dict(doctype=doctype, **values)).insert(set_name=name)
        self.data['records'][key] = dict(doctype=doctype, name=doc.name)
        return doc

    def get(self, key):
        row = self.data['records'][key]
        return frappe.get_doc(row['doctype'], row['name'])


def prepare():
    """Run explicitly after checking that installation created no business data."""
    require_disposable()
    if (directory() / 'synthetic-fixtures.json').exists():
        raise RuntimeError('Fixtures already exist; use another disposable database')
    if frappe.db.count('Company') or frappe.db.count('Booking Order'):
        raise RuntimeError('Fixture preparation requires an empty disposable business database')
    f = Fixtures(empty=True)
    # Native setup creates only test-owned masters; installation never calls this.
    from erpnext.setup.setup_wizard.operations.install_fixtures import install
    install('Pakistan')
    # Reproduce documented native setup, not a prior site's fiscal defaults.
    year=int(nowdate()[:4])
    for value in (year-1,year):
        f.create('fiscal-year-'+str(value),'Fiscal Year',year=str(value),
                 year_start_date=str(value)+'-01-01',year_end_date=str(value)+'-12-31')
    frappe.db.set_value('Currency','PKR','enabled',1)
    for label,buying,selling in [('Standard Buying',1,0),('Standard Selling',0,1)]:
        if not frappe.db.exists('Price List',label):
            f.create('price-list-'+label,'Price List',price_list_name=label,enabled=1,
                     buying=buying,selling=selling,currency='PKR')
    frappe.db.set_single_value('Global Defaults','default_currency','PKR')
    frappe.db.set_single_value('System Settings','time_zone','Asia/Karachi')
    for index in (1, 2):
        company = f.create('company'+str(index), 'Company',
            company_name=f.label+' '+str(index), abbr=('PTA' if index==1 else 'PTB')+f.run[:5],
            country='Pakistan', default_currency='PKR',
            create_chart_of_accounts_based_on='Standard Template', chart_of_accounts='Standard',
            enable_perpetual_inventory=0)
        for field in ('default_income_account','default_expense_account','default_receivable_account',
                      'default_payable_account','cost_center'):
            if not company.get(field): raise RuntimeError('Missing native Company default: '+field)
    company = f.get('company1')
    for name in ('Per Container','Per Bag','Per Weight(Ton)'):
        if not frappe.db.exists('UOM',name):f.create('uom-'+name,'UOM',uom_name=name)
    for name,mode in (('Road (Truck)','Road'),('Rail (Train)','Rail')):
        f.create('mode-'+mode,'Transport Mode',set_name=name,mode=mode)
    parent=frappe.db.get_value('Sales Person',{'is_group':1},'name')
    person=f.create('sales-person','Sales Person',sales_person_name=f.label,
                    parent_sales_person=parent,is_group=0)
    customer=f.create('customer','Customer',customer_name=f.label,customer_type='Company',
        customer_group=frappe.db.get_value('Customer Group',{'is_group':0},'name'),
        territory=frappe.db.get_value('Territory',{'is_group':0},'name'),
        sales_team=[dict(sales_person=person.name,allocated_percentage=100)])
    supplier=f.create('supplier','Supplier',supplier_name=f.label,supplier_type='Company',
        supplier_group=frappe.db.get_value('Supplier Group',{'is_group':0},'name'))
    f.create('commodity','FPL Commodities',comodity_name='Consumer Goods')
    f.create('shipping-line','FPL Shippingline',shipping_line_name=f.label+' Shipping')
    for index in range(1,7):
        f.create('location-'+str(index),'Location',location_name=f.label+' Yard '+str(index),
                 custom_location_type='Yard',custom_disabled=0,is_group=0)
    for index in (1,2):
        f.create('item-'+str(index),'Item',item_code=f.label+' Service '+str(index),
            item_name=f.label+' Service '+str(index),item_group='Services',stock_uom='Per Container',
            is_stock_item=0,is_sales_item=1,is_purchase_item=1,
            uoms=[dict(uom=u,conversion_factor=1) for u in ('Per Container','Per Bag','Per Weight(Ton)','Nos')],
            item_defaults=[dict(company=f.get('company'+str(i)).name,
                income_account=f.get('company'+str(i)).default_income_account,
                expense_account=f.get('company'+str(i)).default_expense_account,
                buying_cost_center=f.get('company'+str(i)).cost_center,
                selling_cost_center=f.get('company'+str(i)).cost_center) for i in (1,2)],
            supplier_items=[dict(supplier=supplier.name)])
    for size in (20,40):
        f.create('container-type-'+str(size),'Container Type',name1=f.label+' '+str(size),
                 size=size,max_cargo_weight_kg=60,tare_weight_kg=2,capacity_m3=60)
    for mode in ('Road (Truck)','Rail (Train)'):
        labels=('Empty Pickup','Long Haul','Short Haul','Empty Return','Cross Stuff') if mode.startswith('Road') else (
            'Empty Pickup','First Mile','Middle Mile','Last Mile','Empty Return','Cross Stuff')
        for label in labels:
            kind='Rail' if label=='Middle Mile' else 'Cross Stuff' if label=='Cross Stuff' else 'Road'
            f.create('service-'+mode+'-'+label,'Service Type',company=company.name,
                name1=label,transport_mode=mode,job_type=kind)
    for label in ('Gate In','Gate Out'):
        f.create('service-'+label,'Service Type',company=company.name,name1=label,job_type='Yard')
    f.create('service-Shifting','Service Type',company=company.name,name1='Shifting',job_type='Road')
    req=json.loads((Path(__file__).parents[1]/'release_requirements.json').read_text())
    for profile,labels in req['service_profiles'].items():
        mode,movement=profile.split('/');mode={'Road':'Road (Truck)','Rail':'Rail (Train)'}[mode]
        for index,label in enumerate(labels,1):
            f.create('sequence-'+profile+'-'+label,'FPL Jobs Sequence',company=company.name,
                sequence=index,transport_mode=mode,sales_order_type=movement,
                service_name=f.get('service-'+mode+'-'+label).name)
    for key,job_mode,amount in [('road-fixed','Truck Job',10),('yard-fixed','Yard Job',2),('cross-fixed','Cross Stuff Job',3)]:
        f.create(key,'FPL Cost Type',company=company.name,cost_name=f.label+' '+key,
            job_mode=job_mode,fixed_=1,cost=amount,item_id=f.get('item-1').name,cargo_supplier=supplier.name)
    f.create('financial-ui-cost','FPL Cost Type',company=company.name,cost_name=f.label+' Extra',
        job_mode='Truck Job',fixed_=0,cost=0,item_id=f.get('item-1').name,cargo_supplier=supplier.name)
    for movement,station in [('Up',5),('Down',6)]:
        f.create('rail-variable-'+movement,'FPL Cost Type',company=company.name,
            cost_name=f.label+' Rail '+movement,job_mode='Train Job',fixed_=0,cost=0,
            movement_type=movement,location=f.get('location-'+str(station)).name,
            item_id=f.get('item-1').name,cargo_supplier=supplier.name,cargo_rail_freight=1)
        f.create('rail-fixed-'+movement,'FPL Cost Type',company=company.name,
            cost_name=f.label+' Terminal '+movement,job_mode='Train Job',fixed_=1,cost=10,
            movement_type=movement,location=f.get('location-'+str(11-station)).name,
            item_id=f.get('item-1').name,cargo_supplier=supplier.name)
    for category in ('Large','Small'):
        f.create('wagon-type-'+category,'FPL Wagons',name1=f.label+' '+category,type=category,
            size='60' if category=='Large' else '40',max_weight_ton=120,max_count=3,state='Empty')
        for size in (20,40):
            f.create('tariff-'+category+'-'+str(size),'Rail Freight Cost',company=company.name,
                wagon_type=category,container_count=int(size==20),container_count_40=int(size==40),
                rate_20=125 if size==20 else 0,rate_40=325 if size==40 else 0)
    f.data['records']['reference-wagon-BFC']=f.data['records']['wagon-type-Large']
    for label,w20,w40,r20,r40,priority in [('A',40,30,100,200,30),('B',30,30,150,175,20),('C',20,40,110,210,10)]:
        f.create('tariff-mixed-'+label,'Rail Freight Cost',company=company.name,wagon_type='Large',
            container_count=1,container_count_40=1,avg_weight=w20,avg_weight_40=w40,
            rate_20=r20,rate_40=r40,cargo_priority=priority)
    roles={'sales-only':['Sales User'], 'accounting':['Sales User','Accounts Manager','Cargo Operator'],
           'operator':['Sales User','Accounts User','Stock User','Cargo Operator'],
           'manager':['Sales Manager','Accounts Manager','Stock Manager','Cargo Manager'], 'denied':['Employee']}
    for profile,grants in roles.items():
        user=f.create('user-'+profile,'User',email='cargo-'+profile+'-'+f.run+'@example.invalid',
            first_name='Synthetic '+profile,send_welcome_email=0,enabled=1,
            roles=[dict(role=role) for role in grants])
        f.create('user-company-'+profile,'User Permission',user=user.name,allow='Company',
            for_value=company.name,apply_to_all_doctypes=1,is_default=1)
    make_booking(f,'Road-Domestic',selected_labels=['Long Haul'])
    # The synthetic setup above supplies the native onboarding prerequisites.
    # Complete only this disposable site's native wizard flags for Desk tests.
    from frappe.desk.page.setup_wizard.setup_wizard import enable_setup_wizard_complete,disable_future_access
    for app in ('frappe','erpnext'):enable_setup_wizard_complete(app)
    disable_future_access()
    frappe.db.commit()
    f.path.write_text(json.dumps(f.data,indent=2)+'\n')
    f.path.chmod(0o600)
    return dict(synthetic=True,run=f.run,records=len(f.data['records']))


class RollbackCase(unittest.TestCase):
    def setUp(self):
        require_disposable()
        self.user=frappe.session.user
        frappe.set_user('Administrator')
        self.f=Fixtures()
        self.uid='PUB-'+uuid.uuid4().hex[:12]
        self.created=[]
        insert=frappe.model.document.Document.db_insert
        def record(doc,*args,**kwargs):
            result=insert(doc,*args,**kwargs)
            self.created.append((doc.doctype,doc.name))
            return result
        self.patches=[patch.object(frappe.db,'commit',side_effect=AssertionError('Unexpected test commit')),
            patch.object(frappe.model.document.Document,'db_insert',record),
            patch('frappe.sendmail'),patch('frappe.enqueue'),patch('frappe.publish_realtime'),
            patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP is disabled'))]
        for p in self.patches:p.start()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            frappe.set_user('Administrator')
            frappe.db.rollback()
            for dt,name in set(self.created):
                self.assertFalse(frappe.db.exists(dt,name),'Synthetic test record survived rollback')
                frappe.clear_document_cache(dt,name)
        finally:
            for p in reversed(self.patches):p.stop()
            frappe.set_user(self.user)


def prepare_browser():
    """Explicit test-only writer; no HTTP whitelist or install-time invocation."""
    require_disposable()
    f=Fixtures()
    booking=make_booking(f,'Browser',selected_labels=['Long Haul'])
    invoice=booking.create_and_submit_sales_invoice()
    f.data['records']['browser-invoice']=dict(doctype='Sales Invoice',name=invoice)
    frappe.db.commit()
    f.path.write_text(json.dumps(f.data,indent=2)+'\n')
    f.path.chmod(0o600)
    return dict(booking=booking.name,invoice=invoice)


@frappe.whitelist()
def browser_context():
    """Read-only destination verification; exposes only disposable test identities."""
    require_disposable()
    frappe.only_for('System Manager')
    f=Fixtures()
    req=json.loads((Path(__file__).parents[1]/'release_requirements.json').read_text())
    return dict(run=f.run,site=frappe.local.site,company=f.get('company1').name,
        booking=f.get('booking-Browser').name,invoice=f.get('browser-invoice').name,
        parents=[name for name in req['original_doctypes']+req['supporting_doctypes']
                 if not frappe.get_meta(name).istable],reports=req['reports'],formats=req['print_formats'])


def make_booking(f, key, mode='Road (Truck)', movement='Domestic', qty=1, rate=100, size=40, avg_weight=20,
                 rate_type='Per Container', bag_qty=0, amount=None, submit=True, selected_labels=None, coherent_route=False, rail_movement='Up',booking_date=None):
    from cargo_management.cargo_management.utils.configuration import catalog
    company, customer = f.get('company1'), f.get('customer')
    sequence = catalog('FPL Jobs Sequence', company.name,
        {'transport_mode': mode, 'sales_order_type': movement}, order_by='sequence asc')
    selected = [row for row in sequence if selected_labels is None or frappe.db.get_value('Service Type', row.service_name, 'name1') in selected_labels]
    computed = rate * (bag_qty if rate_type == 'Per Bag' else qty * avg_weight if rate_type == 'Per Weight(Ton)' else qty)
    values = dict(set_name='BO-TEST-' + f.directory.name + '-' + key, naming_series='BO-.YYYY.-',
        company=company.name, customer=customer.name, bill_to=customer.name, sales_person=f.get('sales-person').name,
        sales_order_date=booking_date or nowdate(), delivery_date=add_days(booking_date or nowdate(), 1), transport_type=mode, sales_order_type=movement,
        bill_of_landing_number=f.label + ' / ' + key,
        services=[dict(services=row.service_name, service_name=frappe.db.get_value('Service Type', row.service_name, 'name1'), applicable=1) for row in selected],
        cargo_details=[dict(cargo_type=f.get('item-1').name, size=size, avg_weight=avg_weight,
                            rate_type=rate_type, rate=rate, qty=qty, bag_qty=bag_qty, amount=computed if amount is None else amount)])
    for prefix in ('long_haul', 'short_haul', 'fm', 'lm', 'empty_pickup', 'empty_return'):
        values[prefix + '_pickup_location'] = f.get('location-1').name
        values[prefix + '_dropoff_location'] = f.get('location-2').name
    values.update(mm_loading_station=f.get('location-1').name, mm_offloading_station=f.get('location-2').name,
                  empty_pickup_location=f.get('location-1').name)
    if 'commodity' in f.data['records']:
        values.update(commodity=f.get('commodity').name,shipping_line=f.get('shipping-line').name)
    if coherent_route:
        costs=catalog('FPL Cost Type',company.name,{'cargo_rail_freight':1,'movement_type':'Up'})
        load=costs[0].location
        other=catalog('FPL Cost Type',company.name,{'fixed_':1,'movement_type':'Up','location':['!=',load]})
        unload=next((row.location for row in other if row.location),f.get('location-6').name)
        if rail_movement=='Down':load,unload=unload,load
        depot,origin,terminal,customer_location=[f.get('location-'+str(index)).name for index in (1,2,3,4)]
        values.update(empty_pickup_location=depot,empty_pickup_dropoff_location=origin,
            long_haul_pickup_location=origin,long_haul_dropoff_location=terminal,
            short_haul_pickup_location=terminal,short_haul_dropoff_location=customer_location,
            fm_pickup_location=origin,fm_dropoff_location=load,mm_loading_station=load,mm_offloading_station=unload,
            lm_pickup_location=unload,lm_dropoff_location=customer_location,
            empty_return_pickup_location=customer_location,empty_return_dropoff_location=depot)
    booking = f.create('booking-' + key, 'Booking Order', **values)
    if submit and booking.docstatus == 0:
        booking.submit()
    return booking


def allocate_freight(f, freight, key):
    import hashlib
    from frappe.utils import now_datetime
    if not freight.container_number:
        number=int(hashlib.sha256((f.directory.name+key).encode()).hexdigest()[:8],16)%10000000
        while frappe.db.exists('FPL Containers',{'container_number':'TEST'+str(number).zfill(7)}):number=(number+1)%10000000
        freight.container_number='TEST'+str(number).zfill(7)
        freight.container_type=f.get('container-type-'+str(freight.size)).name
        freight.documents_received=now_datetime()
        freight.save()
    container=frappe.get_doc('FPL Containers',{'freight_order_id':freight.name,'container_number':freight.container_number})
    f.data['records']['allocation-'+key]=dict(doctype='FPL Containers',name=container.name)
    return container


def complete_road(f, job, at):
    from datetime import timedelta
    if job.status=='Completed':return
    job.vehicle_number='TEST TRUCK '+job.name
    job.vehicle_supplier=f.get('supplier').name
    job.driver_name='Synthetic Cargo Driver'
    job.pickup_arrival=at;job.pickup_departure=at+timedelta(minutes=5)
    job.dropoff_arrival=at+timedelta(minutes=20);job.dropoff_completed=at+timedelta(minutes=25)
    job.save()
    if job.status!='Completed':raise RuntimeError('Road lifecycle did not reach Completed: '+job.name)


def complete_until_rail(f, freight, at):
    from datetime import timedelta
    for index, row in enumerate(list(freight.jobs)):
        freight.reload()
        row=next(value for value in freight.jobs if value.name==row.name)
        if frappe.db.exists('FPLRailJob',row.job_id):break
        if frappe.db.exists('FPLRoadJob',row.job_id):complete_road(f,frappe.get_doc('FPLRoadJob',row.job_id),at+timedelta(minutes=30*index))
        elif frappe.db.exists('FPLYardJob',row.job_id):
            job=frappe.get_doc('FPLYardJob',row.job_id)
            if job.job_name=='Gate Out':break  # Train departure completes its gate-out atomically.
            if job.status!='Completed':
                field='gate_in' if job.job_name=='Gate In' else 'gate_out'
                job.set(field,at+timedelta(minutes=30*index));job.save()


def perform_rail(f, booking, freight, container, key, at, movement='Up', stop_at='Arrived',
                 additional_containers=(), wagon_type_key='reference-wagon-BFC'):
    from datetime import timedelta
    wagon=f.create('flow-wagon-'+key,'Wagons',wagon_number=f.label+' '+key,
                   type=f.get(wagon_type_key).name,status='Received')
    train=f.create('flow-train-'+key,'FPL Perform Middle Mile',company=booking.company,
        rail_number=f.label+' '+key,movement_type=movement,departure_location=booking.mm_loading_station,
        arrival_location=booking.mm_offloading_station,status='Train Formed',finish_train_formation=1,
        expected_departure_time_eda=at+timedelta(hours=2),expected_time_of_arrival_eta=at+timedelta(hours=4),
        wagons=[dict(wagon_number=wagon.name,wagon_type=wagon.type,loaded_=0)])
    if stop_at == 'Train Formed':
        return train
    if not train.finish_loading:
        for allocation in (container, *additional_containers):
            slot=next(row for row in train.middle_mile if not row.container)
            slot.container=allocation.name;slot.wagon_number=wagon.name
        train.loading_time=at+timedelta(hours=1);train.loading_end_time=at+timedelta(hours=2)
        train.finish_loading=1;train.status='Loaded';train.save()
    if stop_at == 'Loaded':
        return train
    if not train.finish_departure:
        for row in train.middle_mile_in_loading:
            if row.container:row.departed_=1
        train.finish_departure=1;train.departure_time=at+timedelta(hours=2,minutes=5);train.status='Departed';train.save()
    if stop_at == 'Departed':
        return train
    if not train.finish_arrival:
        for row in train.middle_mile_copy:
            if row.container:row.received_=1
        train.actual_arrival_datetime=at+timedelta(hours=3)
        train.finish_arrival=1;train.status='Arrived';train.save()
    count=len(train.expenses);invoices=[row.purchase_invoice_no for row in train.expenses]
    train.save();train.reload()
    if len(train.expenses)!=count or [row.purchase_invoice_no for row in train.expenses]!=invoices:
        raise RuntimeError('Repeated rail arrival changed charges or invoice identity')
    for expense in train.expenses:
        f.data['records']['generated-pi-'+expense.purchase_invoice_no]=dict(doctype='Purchase Invoice',name=expense.purchase_invoice_no)
    return train


def cross_case(f, key, existing=True, submit=False):
    """A new owned transfer, using the original Company's verified services."""
    from frappe.utils import now_datetime
    from cargo_management.cargo_management.utils.configuration import resolve_service
    booking = make_booking(f, key, selected_labels=['Long Haul', 'Empty Return'])
    source = frappe.get_doc('FPL Freight Orders', {'sales_order_number': booking.name})
    source_container = allocate_freight(f, source, key + '-source')
    long_haul = resolve_service('Long Haul', 'Road (Truck)', booking.company)
    cross_service = resolve_service('Cross Stuff', 'Road (Truck)', booking.company)
    if existing and not any(row.job_name == cross_service for row in source.jobs):
        source.append('jobs', dict(job_name=cross_service, status='Draft',
            start_location=f.get('location-1').name))
        source.jobs.insert(0, source.jobs.pop())
        for index, row in enumerate(source.jobs, 1):
            row.idx = index
        source.save()
        source.process_jobs()
        source.save()
    request = f.create('request-' + key, 'Container or Vehicle Request', booking_order_id=booking.name,
        yard_location=f.get('location-1').name, cargo_type='Non Containerised',
        table_ktch=[dict(qty=1, size=40, type=f.get('container-type-40').name,
                        pickup_location=f.get('location-2').name)])
    if request.docstatus == 0:
        request.submit()
    target = frappe.get_doc('FPL Freight Orders', {'cargo_request': request.name})
    target_container = allocate_freight(f, target, key + '-receiver')
    # Receiving pickup and gate-in are real operational prerequisites.
    complete_until_rail(f, target, now_datetime())
    performance = f.create('cross-' + key, 'Perform Cross Stuff', booking_order_id=booking.name,
        grounded_yard_location=f.get('location-1').name, job_before_cross_stuff=long_haul,
        total_weight=source.weight, grounded_filled_containers=[dict(container_number=source_container.name,
            reference_container=target_container.name, weight=source.weight,
            weight_to_transfer=source.weight, bags_to_transfer=source.bag_qty,
            empty_return_location=f.get('location-2').name)])
    if submit and performance.docstatus == 0:
        performance.submit()
    return booking, source, target, performance
