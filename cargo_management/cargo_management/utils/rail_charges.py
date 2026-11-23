"""Deterministic rail tariff selection and idempotent received-container charges.

Unique source predicates/prices are preserved. Overlapping rows are never
stacked; incomparable ceilings require explicit Company priorities. Fixed costs
apply once per Cost Type/container, even when both station endpoints coincide.
"""
from decimal import Decimal, InvalidOperation
import hashlib

import frappe
from frappe import _


def number(value):
    try:
        result = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Rail tariff input must be a finite number')
    if not result.is_finite() or result < 0:
        raise ValueError('Rail tariff input must be finite and non-negative')
    return result


def select_tariff(candidates, category, count20, count40, weight20=0, weight40=0):
    original_counts = number(count20), number(count40)
    count20, count40 = int(original_counts[0]), int(original_counts[1])
    if original_counts != (count20, count40):
        raise ValueError('Received container counts must be whole numbers')
    if count20 < 0 or count40 < 0 or not count20 + count40:
        raise ValueError('Received container counts must be positive')
    mixed = count20 == count40 == 1
    weight20, weight40 = number(weight20), number(weight40)
    if mixed and (not weight20 or not weight40):
        raise ValueError('Mixed rail tariffs require positive verified weights for both sizes')
    selected = []
    for row in candidates:
        if row['wagon_type'] != category or int(row.get('container_count') or 0) != count20 or int(row.get('container_count_40') or 0) != count40:
            continue
        if mixed and (number(row.get('avg_weight')) < weight20 or number(row.get('avg_weight_40')) < weight40):
            continue
        number(row.get('rate_20'))
        number(row.get('rate_40'))
        selected.append(row)
    if not selected:
        raise ValueError('No rail tariff matches the received allocation and verified weight boundaries')
    if len(selected) == 1:
        return selected[0]
    if not mixed:
        raise ValueError('Multiple single-size tariffs share the same source predicates; correct the configuration')
    if mixed:
        # A strictly narrower ceiling dominates a broader eligible rectangle.
        frontier = [row for row in selected if not any(
            other is not row and number(other.get('avg_weight')) <= number(row.get('avg_weight'))
            and number(other.get('avg_weight_40')) <= number(row.get('avg_weight_40'))
            and (number(other.get('avg_weight')), number(other.get('avg_weight_40')))
                != (number(row.get('avg_weight')), number(row.get('avg_weight_40')))
            for other in selected)]
    else:
        frontier = selected
    if len(frontier) == 1:
        return frontier[0]
    # Equal boundaries are duplicate/conflicting configuration, never a hidden
    # override by insertion order, name, modification time or arbitrary priority.
    signatures = [(number(row.get('avg_weight')), number(row.get('avg_weight_40'))) for row in frontier]
    if mixed and len(signatures) != len(set(signatures)):
        raise ValueError('Duplicate rail tariff ceilings require configuration correction')
    if not all(int(row.get('cargo_priority') or 0) > 0 for row in frontier):
        raise ValueError('Overlapping rail tariffs require explicit positive Company priorities')
    priority = min(int(row['cargo_priority']) for row in frontier)
    winners = [row for row in frontier if int(row['cargo_priority']) == priority]
    if len(winners) != 1:
        raise ValueError('Rail tariff priority must select exactly one eligible row')
    return winners[0]


def charge_key(train, container, cost):
    return hashlib.sha256(('rail\0' + train + '\0' + container + '\0' + cost).encode()).hexdigest()


def append_train_charges(train):
    from cargo_management.cargo_management.utils.configuration import catalog, train_company, freight_company
    from cargo_management.cargo_management.utils.getSupplierForCostType import get_supplier
    company = train_company(train)
    train.company = company
    old = train.get_doc_before_save()
    if old and any(row.get('cargo_charge_key') for row in old.expenses):
        previous = {(row.container,row.wagon_number) for row in old.middle_mile_copy if row.received_}
        current = {(row.container,row.wagon_number) for row in train.middle_mile_copy if row.received_}
        if previous == current:
            return  # A locked historical charge is never silently recalculated.
    if not train.is_new():
        frappe.db.sql('SELECT name FROM `tabFPL Perform Middle Mile` WHERE name=%s FOR UPDATE', train.name)
    groups, containers_seen = {}, set()
    loaded = {row.container:row for row in train.middle_mile_in_loading if row.container}
    for row in train.middle_mile_copy:
        if not row.received_ or not row.wagon_number or not row.container:
            continue
        if row.container in containers_seen:
            frappe.throw(_('A received container cannot be allocated twice.'))
        containers_seen.add(row.container)
        actual = frappe.db.get_value('FPL Containers', row.container, 'freight_order_id')
        if not actual or (row.fo and row.fo != actual):
            frappe.throw(_('Received rail container has a forged Freight Order reference.'))
        freight = frappe.get_doc('FPL Freight Orders', actual)
        if freight_company(freight) != company:
            frappe.throw(_('A rail allocation cannot cross Companies.'))
        if row.container in loaded:
            freight = frappe._dict(freight.as_dict())
            freight.size = int(loaded[row.container].size)
            freight.weight = float(number(loaded[row.container].weight))
        if freight.size not in (20, 40):
            frappe.throw(_('Rail tariffs support verified 20-foot and 40-foot container sizes.'))
        groups.setdefault(row.wagon_number, []).append((row, freight))
    types = {row.wagon_number: row.wagon_type for row in train.wagons}
    tariffs = catalog('Rail Freight Cost', company)
    costs = catalog('FPL Cost Type', company, {'job_mode': 'Train Job'})
    variable = [row for row in costs if row.get('cargo_rail_freight') or (not row.get('company') and row.name == 'TRAIN FREIGHT')]
    variable = [row for row in variable if row.movement_type == train.movement_type and row.location
                and row.location in (train.departure_location, train.arrival_location)]
    if groups and len(variable) != 1:
        frappe.throw(_('Configure exactly one rail-freight Cost Type matching this Company, movement and station.'))
    fixed = {row.name: row for row in costs if row.fixed_ and number(row.cost) > 0
             and row.movement_type == train.movement_type and row.location
             and row.location in (train.departure_location, train.arrival_location) and row not in variable}
    existing = {row.cargo_charge_key: row for row in train.expenses if row.get('cargo_charge_key')}
    pending = []
    for wagon, allocated in groups.items():
        wagon_type = types.get(wagon)
        category = frappe.db.get_value('FPL Wagons', wagon_type, 'type') if wagon_type else None
        if not category:
            frappe.throw(_('Received wagon requires a valid Cargo wagon type.'))
        by_size = {size: [freight for _, freight in allocated if freight.size == size] for size in (20, 40)}
        averages = {size: sum(number(doc.weight) for doc in rows) / len(rows) if rows else 0 for size, rows in by_size.items()}
        try:
            tariff = select_tariff(tariffs, category, len(by_size[20]), len(by_size[40]), averages[20], averages[40])
        except ValueError as error:
            frappe.throw(str(error))
        for row, freight in allocated:
            assignments = [(variable[0], tariff['rate_20'] if freight.size == 20 else tariff['rate_40'], tariff.name)]
            assignments += [(cost, cost.cost, None) for cost in fixed.values()]
            for cost, amount, tariff_name in assignments:
                key = charge_key(train.name, row.container, cost.name)
                supplier = get_supplier(cost.name, company)
                if not supplier:
                    frappe.throw(_('Rail cost {0} requires an explicit or unique Item Supplier binding.').format(cost.name))
                if key in existing:
                    prior = existing[key]
                    if number(prior.amount) != number(amount) or prior.client != supplier or (prior.get('cargo_tariff') or None) != tariff_name:
                        frappe.throw(_('Existing rail charges differ; historical expenses will not be silently recalculated.'))
                    continue
                pending.append(dict(expense_type=cost.name, client=supplier, container_number=row.container,
                                    amount=float(number(amount)), cargo_charge_key=key, cargo_tariff=tariff_name))
    for values in pending:
        train.append('expenses', values)
