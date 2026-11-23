"""Authoritative new rail allocations and immutable departed loading snapshots."""
import frappe
from frappe import _


def validate_allocations(train):
    from cargo_management.cargo_management.utils.configuration import train_company, validate_train_company
    fields=('middle_mile','middle_mile_in_loading','middle_mile_copy')
    old=train.get_doc_before_save()
    if old and not train.flags.get('cargo_operational_rewind') and any(old.get(field) and not train.get(field)
            for field in ('finish_loading','finish_departure','finish_arrival')):
        frappe.throw(_('Use the controlled operational reversal action; completed phases cannot be unchecked.'))
    if (train.finish_arrival and not train.finish_departure or train.finish_departure and not train.finish_loading
            or train.finish_loading and not train.finish_train_formation):
        frappe.throw(_('Train phase completion flags must follow formation, loading, departure and arrival order.'))
    if old and old.finish_departure and any({row.container for row in old.get(field) if row.container}
            != {row.container for row in train.get(field) if row.container} for field in fields) and not train.flags.get('cargo_operational_rewind'):
        frappe.throw(_('Departed train container manifests cannot be replaced or extended.'))
    allocated=any(row.get('container') for field in fields for row in train.get(field))
    for phase,field,flag in (('loading','middle_mile',None),('departure','middle_mile_in_loading','departed_'),('arrival','middle_mile_copy','received_')):
        completed='finish_'+phase
        if train.get(completed) and not (old and old.get(completed)) and not any(
                row.container and (not flag or row.get(flag)) for row in train.get(field)):
            frappe.throw(_('Train {0} requires at least one verified selected container.').format(phase))
    if allocated:
        company=train_company(train)
        if train.company and train.company!=company:
            frappe.throw(_('Train Company conflicts with its Booking allocations.'))
        train.company=company
    validate_train_company(train)
    wagon_types={row.wagon_number:row.wagon_type for row in train.wagons}
    if len(wagon_types)!=len(train.wagons):frappe.throw(_('A wagon cannot be allocated twice on one train.'))
    for wagon in sorted(wagon_types):
        frappe.db.sql('SELECT name FROM `tabWagons` WHERE name=%s FOR UPDATE',wagon)
        physical=frappe.get_doc('Wagons',wagon)
        if physical.type!=wagon_types[wagon]:frappe.throw(_('Wagon type differs from its physical wagon master.'))
        if physical.train_no and physical.train_no!=train.name:
            previous=frappe.get_doc('FPL Perform Middle Mile',physical.train_no)
            previous.check_permission('write')
            if previous.status not in ('Arrived',''):
                frappe.throw(_('Release this wagon from its existing active train before assigning it again.'))
            if previous.status == 'Arrived' and any(
                    row.container and row.wagon_number == wagon and not row.received_
                    for row in previous.middle_mile_copy):
                frappe.throw(_('This wagon still has unreceived containers on its previous train.'))
    if not allocated:
        return  # Wagon ownership was still checked for an empty formation.
    for field in fields:
        seen=set();groups={}
        prior={row.container:row for row in old.get(field) if row.container} if old else {}
        if old and old.finish_departure and set(prior)!={row.container for row in train.get(field) if row.container} and not train.flags.get('cargo_operational_rewind'):
            frappe.throw(_('Departed train container manifests cannot be replaced or extended.'))
        for row in train.get(field):
            if not row.container:continue
            if row.container in seen:frappe.throw(_('A container cannot occupy multiple wagon slots in one train phase.'))
            seen.add(row.container)
            if row.wagon_number not in wagon_types:frappe.throw(_('Container allocation refers to a wagon outside this train.'))
            container=frappe.get_doc('FPL Containers',row.container)
            container.check_permission('read')
            freight=frappe.get_doc('FPL Freight Orders',container.freight_order_id)
            freight.check_permission('read')
            if row.get('fo') and row.fo!=freight.name:frappe.throw(_('Container Freight Order reference was forged.'))
            previous=prior.get(row.container)
            departed=old and old.finish_departure and previous
            if departed:
                for key in ('wagon_number','mm_job_id','fo','weight','size'):
                    current_value,old_value=row.get(key),previous.get(key)
                    if key=='fo':
                        # A derived read-only Data fetch may be absent on either
                        # side of a native round trip. The immutable container
                        # identity is the authority, never a supplied FO value.
                        current_value=current_value or freight.name
                        old_value=old_value or freight.name
                    if key in ('weight','size'):
                        current_value,old_value=float(current_value or 0),float(old_value or 0)
                    if row.meta.has_field(key) and current_value!=old_value:
                        frappe.throw(_('Departed rail allocation snapshot field {0} cannot be rewritten.').format(key))
                if previous.get('received_') and not row.get('received_'):
                    frappe.throw(_('A received allocation requires a controlled reversal; it cannot be unchecked.'))
            else:
                row.fo=freight.name
                row.container_number=container.container_number
                if row.meta.has_field('weight'):row.weight=str(freight.weight)
                if row.meta.has_field('size'):row.size=str(freight.size)
                jobs=frappe.get_all('FPLRailJob',filters={'freight_order_id':freight.name,'cargo_retired':0},pluck='name')
                if len(jobs)!=1 or (row.mm_job_id and row.mm_job_id!=jobs[0]):
                    frappe.throw(_('Rail allocation requires one verified Middle Mile job.'))
                row.mm_job_id=jobs[0]
            groups.setdefault(row.wagon_number,[]).append((row,freight))
        if field=='middle_mile_copy':continue  # It uses the immutable loading grid for physical capacity.
        for wagon,allocated in groups.items():
            profile=frappe.get_doc('FPL Wagons',wagon_types[wagon])
            if len(allocated)>profile.max_count or sum(int(row.size or 0) for row,_ in allocated)>int(profile.size or 0):
                frappe.throw(_('Wagon count or container-length capacity was exceeded.'))
            if sum(float(row.weight or 0) for row,_ in allocated)>profile.max_weight_ton:
                frappe.throw(_('Wagon weight capacity was exceeded.'))
