"""Permission-aware Cargo report projections with one value per source identity.

No physical container-number joins: allocations, expenses and revenue are keyed
by actual document IDs. Legacy inferred values are labelled and unknown billing
is represented as unknown, never fabricated as a zero.
"""
from collections import defaultdict
from datetime import datetime
import hashlib
import importlib

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime

JOBS = ('FPLRoadJob', 'FPLRailJob', 'FPLYardJob', 'FPLCrossStuffJob')
PARENTS = ('FPLRoadJob', 'FPLYardJob', 'FPL Perform Middle Mile', 'Perform Cross Stuff')


def column(name, label=None, kind='Data', options=None):
    result = dict(fieldname=name, label=_(label or name.replace('_', ' ').title()), fieldtype=kind, width=150)
    if options:
        result['options'] = options
    return result


def original_columns(name, rows, extra):
    module = importlib.import_module('cargo_management.cargo_management.report.' + frappe.scrub(name) + '.' + frappe.scrub(name))
    helper = getattr(module, 'get_columns', None)
    if not helper:
        return extra
    import inspect
    columns = helper(rows, []) if len(inspect.signature(helper).parameters) == 2 else helper()
    names = {row['fieldname'] for row in columns}
    return columns + [row for row in extra if row['fieldname'] not in names]


def booking_scope(filters):
    filters = frappe._dict(filters or {})
    if not frappe.has_permission('Booking Order', 'read'):
        frappe.throw(_('Cargo Booking read permission is required.'), frappe.PermissionError)
    query = {}
    if filters.company: query['company'] = filters.company
    if filters.transport_mode: query['transport_type'] = filters.transport_mode
    if filters.booking_order: query['name'] = filters.booking_order
    output = {}
    for name in frappe.get_list('Booking Order', filters=query, pluck='name', limit_page_length=0):
        doc = frappe.get_doc('Booking Order', name)
        if filters.from_date and getdate(doc.sales_order_date) < getdate(filters.from_date): continue
        if filters.to_date and getdate(doc.sales_order_date) > getdate(filters.to_date): continue
        if filters.customer and doc.customer != filters.customer: continue
        output[name] = doc
    return output


def projection(filters=None):
    bookings = booking_scope(filters)
    rows = {}
    if not bookings:
        return rows
    for name in frappe.get_list('FPL Freight Orders', filters={'sales_order_number': ['in', list(bookings)]}, pluck='name', limit_page_length=0):
        freight = frappe.get_doc('FPL Freight Orders', name)
        booking = bookings[freight.sales_order_number]
        revenue, origin = freight.get('cargo_contracted_revenue'), 'Versioned native billing contract'
        if not freight.get('cargo_billing_version'):
            if freight.rate_type == 'Per Container': revenue = freight.rate
            elif freight.rate_type == 'Per Bag': revenue = (freight.rate or 0) * (freight.bag_qty or 0)
            elif freight.rate_type == 'Per Weight(Ton)': revenue = (freight.rate or 0) * (freight.weight or 0)
            else: revenue = None
            origin = 'Legacy rate inference' if revenue is not None else 'Unresolved legacy billing allocation'
            if revenue is None and freight.get('cargo_request'):
                origin = 'Pending Cross-Stuff contract allocation'
        row = frappe._dict(FOname=name, FONumber=name, FO_status=freight.status, CName=name,
            container_number=freight.container_number, BOName=booking.name, BOdate=booking.sales_order_date,
            company=booking.company, BOcustomer=booking.customer, bill_to=booking.bill_to, cargo_owner=booking.cargo_owner,
            sales_person=booking.sales_person, sales_order_type=booking.sales_order_type, transport_type=booking.transport_type,
            BODdate=booking.delivery_date, commodity=booking.commodity, pickup_location=booking.pickup_location, dropoff_location=booking.dropoff_location,
            size=freight.size, weight=freight.weight, f_weight=freight.weight, bag_qty=freight.bag_qty,
            total_cost=0, extra_cost=0, posted_extra_revenue=0, selling_cost=revenue, profit=None, billing_basis=origin,
            booking_submission_status={0:'Draft',1:'Submitted',2:'Cancelled'}[booking.docstatus],
            jobs=[], expenses=[], freight=freight, booking=booking)
        for child in freight.jobs:
            if child.get('cargo_retired'):
                continue
            for kind in JOBS:
                if frappe.db.exists(kind, child.job_id) and frappe.has_permission(kind, 'read', doc=child.job_id):
                    job = frappe.get_doc(kind, child.job_id)
                    if not job.get('cargo_retired'):
                        row.jobs.append(job)
                    break
        rows[name] = row
    seen = set()
    for kind in PARENTS:
        if not frappe.has_permission(kind, 'read'):
            continue
        query = {}
        if kind in ('FPLRoadJob','FPLYardJob'): query['sales_order_number'] = ['in', list(bookings)]
        elif kind == 'Perform Cross Stuff': query['booking_order_id'] = ['in', list(bookings)]
        for name in frappe.get_list(kind, filters=query, pluck='name', limit_page_length=0):
            parent = frappe.get_doc(kind, name)
            for expense in parent.get('expenses') or []:
                if expense.name in seen:
                    continue
                freight = frappe.db.get_value('FPL Containers', expense.container_number, 'freight_order_id') if expense.container_number else parent.get('freight_order_id')
                if freight not in rows:
                    continue
                row = rows[freight]
                if parent.get('sales_order_number') and parent.sales_order_number != row.BOName: continue
                if parent.get('booking_order_id') and parent.booking_order_id != row.BOName: continue
                if parent.get('company') and parent.company != row.company: continue
                seen.add(expense.name)
                row.expenses.append(expense)
                row.total_cost += expense.amount or 0
                if expense.invoiced_: row.extra_cost += expense.amount or 0
                if expense.sales_invoice_no and frappe.db.get_value('Sales Invoice', expense.sales_invoice_no, 'docstatus') == 1:
                    row.posted_extra_revenue += expense.amount or 0
                stage = parent.get('job_name') or ('Middle Mile' if kind == 'FPL Perform Middle Mile' else 'Cross Stuff')
                label = stage + ' - ' + (frappe.db.get_value('FPL Cost Type', expense.expense_type, 'cost_name') or expense.expense_type)
                key = 'cost_' + hashlib.sha256((stage + '\0' + expense.expense_type).encode()).hexdigest()[:12]
                row[key] = row.get(key, 0) + (expense.amount or 0)
                row.setdefault('cost_labels', {})[key] = label
                if kind == 'FPL Perform Middle Mile':
                    row.rail_number, row.train, row.movement_type, row.loco_number = parent.rail_number, parent.name, parent.movement_type, parent.loco_number
    for row in rows.values():
        row.profit = row.selling_cost + row.posted_extra_revenue - row.total_cost if row.selling_cost is not None else None
    return rows


def pnl(name, filters):
    rows = list(projection(filters).values())
    if name == 'Road PNL Container Wise': rows = [r for r in rows if r.transport_type == 'Road (Truck)']
    if name in ('RAIL PNL NEW', 'Rail PNL Container Wise'): rows = [r for r in rows if r.transport_type == 'Rail (Train)']
    columns = [column('BOName','Booking Order','Link','Booking Order'), column('FOname','Freight Order','Link','FPL Freight Orders'),
               column('company',kind='Link',options='Company'),column('container_number'),column('size','Size','Int'),
               column('weight','Weight (Ton)','Float'),column('BOcustomer','Customer','Link','Customer'),column('rail_number'),
               column('billing_basis'),column('selling_cost','Contracted Revenue','Currency'),
               column('total_cost','Cost','Currency'),column('extra_cost','Billable Extra Charges','Currency'),
               column('posted_extra_revenue','Posted Extra Revenue','Currency'),column('profit','Profit','Currency')]
    costs = {key: label for row in rows for key,label in row.get('cost_labels',{}).items()}
    columns += [column(key,label,'Currency') for key,label in sorted(costs.items())]
    if filters.get('train_nos'):
        trains = set(filters['train_nos'])
        rows = [row for row in rows if row.get('train') in trains]
    group = ('BOcustomer' if name == 'Customer PNL' else 'BOName') if filters.get('summaries') else None
    if group:
        groups = {}
        for row in rows:
            key = row[group]
            target = groups.setdefault(key, frappe._dict({group:key,'selling_cost':0,'total_cost':0,'extra_cost':0,'posted_extra_revenue':0,'profit':0}))
            for field in ('selling_cost','total_cost','extra_cost','posted_extra_revenue','profit'):
                target[field] = None if target[field] is None or row[field] is None else target[field] + row[field]
        rows = list(groups.values())
        columns = [column(group,'Customer' if group=='BOcustomer' else 'Booking Order','Link','Customer' if group=='BOcustomer' else 'Booking Order')] + [c for c in columns if c['fieldname'] in ('selling_cost','total_cost','extra_cost','posted_extra_revenue','profit')]
    result = [{k:v for k,v in row.items() if k not in ('jobs','expenses','freight','booking','cost_labels')} for row in rows]
    return (original_columns(name, result, columns) if not group else columns), result


def status(filters):
    filters = frappe._dict(filters or {})
    # Native controls are mutually exclusive. Preserve the legacy Booking-mode
    # precedence if both switches are supplied, and the accepted broad overview.
    train_mode = (filters.transport_mode == 'Rail (Train)' and frappe.utils.cint(filters.check_train)
                  and not frappe.utils.cint(filters.check_booking))
    selected = []
    if train_mode:
        selected = filters.train_nos if filters.train_nos is not None else []
        if isinstance(selected, str):
            try:
                selected = frappe.parse_json(selected)
            except (TypeError, ValueError):
                frappe.throw(_('Train selection must be a list of document names.'))
        if not isinstance(selected, list) or any(not isinstance(name, str) or not name.strip() for name in selected):
            frappe.throw(_('Train selection must be a list of document names.'))
        # Hidden Booking dates may remain in the browser's filter state. v15's
        # train-selection path uses train identity, not the Booking date range.
        filters.pop('from_date', None)
        filters.pop('to_date', None)
    rows = list(projection(filters).values())
    if train_mode:
        readable = set(frappe.get_list('FPL Perform Middle Mile',
            filters={'name': ['in', sorted(set(selected))]}, pluck='name', limit_page_length=0)) if selected else set()
        rows = [row for row in rows if row.FO_status != 'Draft' and any(
            job.doctype == 'FPLRailJob' and job.train_number in readable for job in row.jobs)]
    labels = sorted({job.get('job_name') or frappe.db.get_value('Service Type', job.job_type, 'name1') for row in rows for job in row.jobs})
    columns = [column('BOName','Booking Order','Link','Booking Order'),column('FOname','Freight Order','Link','FPL Freight Orders'),
               column('container_number'),column('FO_status','Freight Status'),column('booking_submission_status','Booking Submission Status')]
    columns += [column(frappe.scrub(label)+'_status',label) for label in labels if label]
    output = []
    for row in rows:
        item = {key:row.get(key) for key in ('BOName','FOname','container_number','FO_status','booking_submission_status')}
        for job in row.jobs:
            label=job.get('job_name') or frappe.db.get_value('Service Type',job.job_type,'name1')
            item[frappe.scrub(label)+'_status'] = job.status
        request = frappe.get_list('Container or Vehicle Request',filters={'booking_order_id':row.BOName},fields=['name','cross_stuff_performance'],limit_page_length=0)
        item['req_status'] = 'Yes' if request else 'No'
        item['crossstuff_status'] = 'Completed' if any(r.cross_stuff_performance for r in request) else ''
        output.append(item)
    return columns+[column('req_status','Request'),column('crossstuff_status','Cross-Stuff')],output


def delivery(filters, name='Delivery Report SQL'):
    rows=[]
    labels=('Empty Pickup','First Mile','Long Haul','Short Haul','Middle Mile','Last Mile','Empty Return')
    columns=[column('BOName','Booking Order','Link','Booking Order'),column('FONumber','Freight Order','Link','FPL Freight Orders'),column('CName','Container Number')]
    for label in labels:
        prefix=label.replace(' ','_')
        columns += [column(prefix+'_Start',label+' Start','Datetime'),column(prefix+'_End',label+' End','Datetime'),column(prefix+'_Duration',label+' Duration (Days)','Float')]
    columns += [column('Gate_In',kind='Datetime'),column('Gate_Out',kind='Datetime'),column('rail_number')]
    for row in projection(filters).values():
        if row.FO_status == 'Draft': continue
        value=dict(BOName=row.BOName,FONumber=row.FOname,CName=row.container_number)
        for job in row.jobs:
            label=job.get('job_name') or frappe.db.get_value('Service Type',job.job_type,'name1')
            if job.doctype=='FPLRailJob' and job.train_number and frappe.has_permission('FPL Perform Middle Mile','read',doc=job.train_number):
                train=frappe.get_doc('FPL Perform Middle Mile',job.train_number)
                start,end=train.departure_time,train.actual_arrival_datetime
                value['rail_number'] = train.rail_number
            else:
                start,end=job.get('pickup_arrival'),job.get('dropoff_completed')
            if label in labels:
                prefix=label.replace(' ','_')
                value[prefix+'_Start'],value[prefix+'_End']=start,end
                value[prefix+'_Duration']=(get_datetime(end)-get_datetime(start)).total_seconds()/86400 if start and end else None
            elif label=='Gate In':
                gate=job.get('gate_in')
                value['Gate_In']=min(filter(None,[value.get('Gate_In'),gate]),default=None)
            elif label=='Gate Out':
                gate=job.get('gate_out')
                value['Gate_Out']=max(filter(None,[value.get('Gate_Out'),gate]),default=None)
        rows.append(value)
    if name=='Delivery report':
        for row in rows:
            row.update({key.lower():value for key,value in list(row.items()) if key.endswith(('_Start','_End','_Duration'))})
        module=importlib.import_module('cargo_management.cargo_management.report.delivery_report.delivery_report')
        columns=module.get_columns(rows,list(labels))+[column('FONumber','Freight Order','Link','FPL Freight Orders'),column('rail_number')]
    return columns,rows


def last_mile(filters):
    output=[]
    for row in projection(filters).values():
        trains={job.train_number for job in row.jobs if job.doctype=='FPLRailJob' and job.train_number
                and frappe.has_permission('FPL Perform Middle Mile','read',doc=job.train_number)}
        for job in row.jobs:
            if job.doctype=='FPLRoadJob' and job.get('job_name')=='Last Mile' and job.status=='Assigned':
                for train in sorted(trains):
                    output.append(dict(name=job.name,container_number=row.container_number,train_number=train,status=job.status))
    return [column('name','Job Name','Link','FPLRoadJob'),column('container_number'),
            column('train_number','Train Number','Link','FPL Perform Middle Mile'),column('status')],output


def diagnostic(name,filters):
    columns=[column('freight_order','Freight Order','Link','FPL Freight Orders'),column('container_number'),
             column('service'),column('job_id'),column('status'),column('start_location','Start Location','Link','Location'),column('end_location','End Location','Link','Location')]
    rows=[]
    for row in projection(filters).values():
        freight=row.freight
        if filters.get('freight_order') and freight.name!=filters['freight_order']: continue
        if name=='Query report' and not (freight.last_job=='Gate In' and freight.next_job=='Gate Out' and not freight.mm_completed_): continue
        for child in freight.jobs:
            label=frappe.db.get_value('Service Type',child.job_name,'name1')
            if name=='Query report' and label!='Middle Mile':continue
            rows.append(dict(freight_order=freight.name,container_number=freight.container_number,service=label,
                             job_id=child.job_id,status=child.status,start_location=child.start_location,end_location=child.end_location))
    return columns,rows


def trains(name,filters):
    columns=[column('train','Train','Link','FPL Perform Middle Mile'),column('rail_number'),column('company',kind='Link',options='Company'),
             column('status'),column('departure_location'),column('arrival_location'),column('container_number'),column('wagon_number'),
             column('received','Received','Check'),column('containers','Allocated Containers','Int')]
    query={}
    output=[];selected_docs=[]
    for key in frappe.get_list('FPL Perform Middle Mile',filters=query,pluck='name',limit_page_length=0):
        doc=frappe.get_doc('FPL Perform Middle Mile',key)
        from cargo_management.permissions import legacy_train_company
        company=doc.company or legacy_train_company(doc.name)
        if filters.get('company') and company!=filters['company']:continue
        if filters.get('movement') and doc.movement_type != filters['movement']:continue
        if filters.get('train_no_from') and filters.get('train_no_to'):
            first,last=sorted([get_datetime(filters['train_no_from']),get_datetime(filters['train_no_to'])])
            if not doc.departure_time or not first<=get_datetime(doc.departure_time)<=last:continue
        wanted=filters.get('train_nos') or filters.get('train_no')
        if isinstance(wanted,str): wanted=[wanted]
        if wanted and doc.name not in wanted and doc.rail_number not in wanted:continue
        selected_docs.append(doc)
        values=dict(train=doc.name,rail_number=doc.rail_number,company=company,status=doc.status,
                    departure_location=doc.departure_location,arrival_location=doc.arrival_location,
                    train_no=doc.rail_number,loco_no=doc.loco_number,break_no=doc.break_number,movement=doc.movement_type,
                    loading_start=doc.loading_time,loading_end=doc.loading_end_time,departure_date=doc.departure_time,arrival_date=doc.actual_arrival_datetime)
        allocated=doc.middle_mile_copy or doc.middle_mile_in_loading or doc.middle_mile
        if name=='Trains summary':
            from frappe.utils import format_duration
            unique={row.container:row for row in allocated if row.container}
            sizes=[frappe.db.get_value('FPL Freight Orders',frappe.db.get_value('FPL Containers',container,'freight_order_id'),'size') for container in unique]
            types=[frappe.db.get_value('FPL Wagons',row.wagon_type,'type') for row in doc.wagons]
            values.update(containers=len(unique),t_cont=len(unique),count_20=sizes.count(20),count_40=sizes.count(40),
                loaded_wagons=sum(bool(row.loaded_) for row in doc.wagons),empty_wagons=sum(not row.loaded_ for row in doc.wagons),
                large_wagons=types.count('Large'),small_wagons=types.count('Small'),conventional_wagons=types.count('Conventional'),t_wagons=len(doc.wagons),
                loading_duration=format_duration((get_datetime(doc.loading_end_time)-get_datetime(doc.loading_time)).total_seconds()) if doc.loading_time and doc.loading_end_time else '',
                transit_time=format_duration((get_datetime(doc.actual_arrival_datetime)-get_datetime(doc.departure_time)).total_seconds()) if doc.departure_time and doc.actual_arrival_datetime else '')
            output.append(values)
        else:
            for row in allocated:
                if row.container and frappe.has_permission('FPL Containers','read',doc=row.container):
                    container=frappe.get_doc('FPL Containers',row.container)
                    freight=frappe.get_doc('FPL Freight Orders',container.freight_order_id)
                    booking=frappe.get_doc('Booking Order',freight.sales_order_number)
                    item=dict(values,container_number=container.container_number,container_no=container.container_number,
                        wagon_number=row.wagon_number,wagon_no=row.wagon_number,received=row.get('received_') or 0,
                        size=freight.size,weight=freight.weight,seal_no=freight.seal_no,shipping_line=booking.shipping_line,
                        consignee=booking.bill_to,bill_of_landing_number=booking.bill_of_landing_number,
                        sales_person=booking.sales_person,pod=booking.mm_offloading_station,
                        status='Received' if row.get('received_') else 'Not Received' if doc.finish_arrival else 'In-transit' if doc.finish_departure else 'Loaded')
                    gate=next((job for job in frappe.get_all('FPLYardJob',filters={'freight_order_id':freight.name,'status':'Completed'},fields=['gate_in']) if job.gate_in),None)
                    item['grounded_datetime']=gate.gate_in if gate else None
                    output.append(item)
    columns=original_columns(name,output,columns)
    if name=='Train Detail':
        summary=[dict(label=label,value=sum(row['status']==label for row in output),datatype='Int') for label in ('Loaded','In-transit','Received','Not Received')]
        summary.insert(0,dict(label='Total Containers',value=len(output),datatype='Int'))
        selected=selected_docs[0] if len(selected_docs)==1 else None
        summary += [dict(label=label,value=selected.get(field) if selected else None) for label,field in (
            ('Departure Location','departure_location'),('Arrival Location','arrival_location'),('Engine Number','loco_number'),
            ('Break Number','break_number'),('Departure Time','departure_time'),('Arrival Time','actual_arrival_datetime'),('Train Status','status'))]
        return columns,output,None,None,summary,dict(total_containers=len(output))
    return columns,output


def grounded(name,filters):
    columns=[column('yard','Yard','Link','Location'),column('container_number'),column('BOName','Booking Order','Link','Booking Order'),
             column('FOname','Freight Order','Link','FPL Freight Orders'),column('size','Size','Int'),column('gate_in',kind='Datetime'),column('days','Grounded Days','Float')]
    output=[]
    from datetime import timedelta
    cutoff=get_datetime(filters.get('to_date') or now_datetime())
    if filters.get('gate_in_date'): cutoff=get_datetime(getdate(filters['gate_in_date']))+timedelta(days=1)
    for row in projection(filters).values():
        active=[job for job in row.jobs if job.doctype=='FPLYardJob']
        entered=[job for job in active if job.get('gate_in') and get_datetime(job.gate_in)<=cutoff]
        exited=[job for job in active if job.get('gate_out') and get_datetime(job.gate_out)<=cutoff]
        if not entered:continue
        latest=max(entered,key=lambda job:get_datetime(job.gate_in))
        if any(get_datetime(job.gate_out)>=get_datetime(latest.gate_in) for job in exited):continue
        yard=latest.job_start_location
        wanted_yard=filters.get('gate_in_location') or filters.get('yard_location')
        if wanted_yard and yard!=wanted_yard:continue
        if filters.get('container_size') and int(filters['container_size'])!=row.size:continue
        output.append(dict(yard=yard,container_number=row.container_number,container_no=row.container_number,BOName=row.BOName,FOname=row.FOname,
            size=row.size,gate_in=latest.gate_in,gate_in_datetime=latest.gate_in,gate_out_datetime=None,
            days=(cutoff-get_datetime(latest.gate_in)).total_seconds()/86400,weight=row.weight,seal_no=row.freight.seal_no,
            shipping_line=row.booking.shipping_line,consignee=row.bill_to,bill_of_landing_number=row.booking.bill_of_landing_number,
            pod=row.booking.mm_offloading_station,sales_person=row.sales_person,bo_type=row.sales_order_type,status='LOADED'))
    if 'Summary' in name:
        groups={}
        for row in output:
            key=(row['yard'],getdate(row['gate_in']))
            group=groups.setdefault(key,dict(terminal=row['yard'],twenty_feet_containers=0,forty_feet_containers=0,total_weight=0,rows=[]))
            group['twenty_feet_containers']+=int(row['size']==20);group['forty_feet_containers']+=int(row['size']==40)
            group['total_weight']+=row['weight'] or 0;group['rows'].append(row)
        output=[]
        for (yard,date),group in sorted(groups.items()):
            values={key:value for key,value in group.items() if key!='rows'}
            for field in ('consignee','bill_of_landing_number','sales_person','bo_type','status'):
                values[field]=', '.join(sorted({str(row[field]) for row in group['rows'] if row[field]}))
            values.update(yard=yard,date=date);output.append(values)
        module=importlib.import_module('cargo_management.cargo_management.report.yard_&_date_wise_grounded_container_summary.yard_&_date_wise_grounded_container_summary')
        summary,primitive=module.get_summary(output)
        return original_columns(name,output,[column('date',kind='Date')]),output,None,None,summary,primitive
    for index,row in enumerate(output,1):row['s_no']=index
    return original_columns(name,output,columns),output


def execute_report(name, filters=None):
    filters=frappe._dict(filters or {})
    if name in ('Booking PNL','Customer PNL','RAIL PNL NEW','Rail PNL Container Wise','Road PNL Container Wise'):
        return pnl(name,filters)
    if name=='Job Status':return status(filters)
    if name in ('Child doc type testing','Query report'):return diagnostic(name,filters)
    if name in ('Delivery report','Delivery Report SQL'):return delivery(filters,name)
    if name=='Last Mile with Rail No':return last_mile(filters)
    if name in ('Train Detail','Trains summary'):return trains(name,filters)
    if name in ('Yard & Date wise Grounded Container Summary','Yard and Date wise Grounded Container'):return grounded(name,filters)
    if name=='Pending BOs for Cross Stuff':
        scope=booking_scope(filters);rows=[]
        for booking in scope.values():
            if booking.location_of_cross_stuff and not frappe.get_list('Container or Vehicle Request', filters={'booking_order_id':booking.name}, pluck='name', limit_page_length=1):
                rows.append(dict(booking_order=booking.name))
        return [column('booking_order','Booking Order','Link','Booking Order')],rows
    raise ValueError('Unknown Cargo report')
