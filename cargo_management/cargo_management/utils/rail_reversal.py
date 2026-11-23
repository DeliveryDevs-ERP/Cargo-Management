"""Atomic operational rewinds, never accounting reversals or arrival undo."""
import uuid

import frappe


def rewind(name, phase):
    train = frappe.get_doc('FPL Perform Middle Mile', name, for_update=True)
    train.check_permission('write')
    if train.finish_arrival or train.status == 'Arrived' or train.expenses or any(row.received_ for row in train.middle_mile_copy):
        frappe.throw('Received or cost-bearing trains require controlled financial reversal and cannot be rewound.')
    if phase == 'loading' and train.finish_departure:
        frappe.throw('Cancel departure before cancelling loading.')
    if not train.get('finish_' + phase):
        return {'name': train.name, 'status': train.status, 'unchanged': True}
    jobs = []
    for row in train.middle_mile_in_loading:
        if not row.container:
            continue
        container = frappe.get_doc('FPL Containers', row.container, for_update=True)
        container.check_permission('write')
        freight = frappe.get_doc('FPL Freight Orders', container.freight_order_id, for_update=True)
        freight.check_permission('write')
        for step in freight.jobs:
            kind = 'FPLYardJob' if frappe.db.exists('FPLYardJob', step.job_id) else 'FPLRailJob' if frappe.db.exists('FPLRailJob', step.job_id) else None
            if kind:
                job = frappe.get_doc(kind, step.job_id, for_update=True)
                if job.get('cargo_retired') or (job.get('job_name') == 'Gate Out' and job.expenses):
                    frappe.throw('Retired or cost-bearing gate work cannot be rewound automatically.')
                if kind == 'FPLRailJob' and job.status == 'Completed':
                    frappe.throw('Completed rail work cannot be rewound automatically.')
        jobs.append((container, freight))
    savepoint = 'cargo_rail_rewind_' + uuid.uuid4().hex[:12]
    frappe.db.savepoint(savepoint)
    try:
        if phase == 'departure':
            for container, freight in jobs:
                gate = None
                for step in freight.jobs:
                    if frappe.db.exists('FPLYardJob', step.job_id):
                        job = frappe.get_doc('FPLYardJob', step.job_id)
                        if job.job_name == 'Gate Out' and job.gate_out:
                            job.gate_out = None
                            job.status = 'Assigned'
                            job.save()
                            step.status = 'Assigned'
                            gate = job.name
                    elif frappe.db.exists('FPLRailJob', step.job_id):
                        step.status = 'Assigned'
                freight.last_job = 'Gate In'
                freight.next_job = 'Gate Out'
                freight.save()
                frappe.db.set_value('FPL Containers', container.name, {'active_job_id': gate, 'state': 'Loaded'})
            train.finish_departure = 0
            train.departure_time = None
            train.set('middle_mile_copy', [])
            for row in train.middle_mile_in_loading:
                row.departed_ = 0
            train.status = 'Loaded'
        else:
            train.finish_loading = 0
            train.loading_time = train.loading_end_time = None
            train.set('middle_mile_in_loading', [])
            train.set('middle_mile_copy', [])
            train.status = 'Train Formed'
            for row in train.wagons:
                row.loaded_ = 0
        for row in train.wagons:
            wagon = frappe.get_doc('Wagons', row.wagon_number, for_update=True)
            if wagon.train_no and wagon.train_no != train.name:
                frappe.throw('Wagon ownership changed; reload the train before reversal.')
            frappe.db.set_value('Wagons', wagon.name, {'status': 'Loaded' if phase == 'departure' and row.loaded_ else 'Received',
                'loaded_': row.loaded_, 'train_no': train.name})
        train.flags.cargo_operational_rewind = True
        train.save()
        return {'name': train.name, 'status': train.status}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
