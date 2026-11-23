"""Company-scoped Cargo catalogs, with unchanged blank-company legacy fallback.

A Company catalog is exclusive as a whole. Missing rows in a partially configured
Company must never be filled from a different Company's or the shared catalog.
"""
import frappe
from frappe import _

CATALOGS = {'Service Type', 'FPL Jobs Sequence', 'FPL Cost Type', 'Rail Freight Cost'}


@frappe.whitelist()
def get_train_company_context():
    """Selectable Company context; never trusts a browser default or ownership."""
    if not (frappe.has_permission('FPL Perform Middle Mile', 'create')
            or frappe.has_permission('FPL Perform Middle Mile', 'read')):
        frappe.throw(_('Cargo train access is required.'), frappe.PermissionError)
    from cargo_management.permissions import allowed_companies
    allowed = allowed_companies(doctype='FPL Perform Middle Mile')
    companies = frappe.get_list('Company', pluck='name', limit_page_length=0, order_by='name')
    if allowed is not None:
        companies = [name for name in companies if name in allowed]
    return dict(companies=companies, sole_company=companies[0] if len(companies) == 1 else None)


def validate_train_company(train):
    """A new empty train still requires authorized, persistent ownership."""
    if train.is_new() and not train.get('company'):
        context = get_train_company_context()
        train.company = context['sole_company']
        if not train.company:
            frappe.throw(_('Select the Company for this Cargo train.'))
    if train.get('company') and not frappe.has_permission('Company', 'read', doc=train.company):
        frappe.throw(_('The selected train Company is not permitted.'), frappe.PermissionError)
    from cargo_management.permissions import allowed_companies
    allowed = allowed_companies(doctype='FPL Perform Middle Mile')
    if train.get('company') and allowed is not None and train.company not in allowed:
        frappe.throw(_('The selected train Company is not permitted.'), frappe.PermissionError)


def booking_company(booking, permission=None):
    if not booking or not frappe.db.exists('Booking Order', booking):
        frappe.throw(_('A valid Cargo Booking Order is required.'))
    doc = frappe.get_doc('Booking Order', booking)
    if permission:
        doc.check_permission(permission)
    if not doc.company:
        frappe.throw(_('Booking {0} has no Company.').format(booking))
    return doc.company


def freight_company(freight, permission=None):
    doc = frappe.get_doc('FPL Freight Orders', freight) if isinstance(freight, str) else freight
    if permission:
        doc.check_permission(permission)
    return booking_company(doc.sales_order_number)


def catalog_filters(doctype, company=None, filters=None):
    if doctype not in CATALOGS:
        raise ValueError('Unsupported Cargo configuration catalog')
    result = dict(filters or {})
    if not frappe.get_meta(doctype).has_field('company'):
        return result
    if company and frappe.db.exists(doctype, {'company': company}):
        result['company'] = company
    else:
        result['company'] = ['is', 'not set']
    return result


def catalog(doctype, company=None, filters=None, fields=None, order_by=None):
    return frappe.get_all(doctype, filters=catalog_filters(doctype, company, filters),
                          fields=fields or ['*'], order_by=order_by or 'name asc', limit_page_length=0)


def validate_binding(doctype, name, company):
    doc = frappe.get_doc(doctype, name)
    if doc.get('company') and doc.company != company:
        frappe.throw(_('{0} {1} belongs to another Company.').format(doctype, name))
    return doc


def resolve_service(label, mode=None, company=None, explicit=None):
    filters = {'name1': label}
    if mode and label not in ('Gate In', 'Gate Out'):
        filters['transport_mode'] = mode
    if explicit:
        doc = validate_binding('Service Type', explicit, company)
        if doc.name1 != label or (mode and label not in ('Gate In', 'Gate Out') and doc.transport_mode != mode):
            frappe.throw(_('Stored Cargo service does not match the requested behavior.'))
        return explicit
    rows = catalog('Service Type', company, filters, fields=['name'])
    if len(rows) != 1:
        frappe.throw(_('Cargo service {0} / {1} requires one unambiguous Company or shared binding; found {2}.')
                     .format(label, mode or _('any mode'), len(rows)))
    return rows[0].name


def ordered_services(booking, selected):
    rows = catalog('FPL Jobs Sequence', booking.company,
                   {'transport_mode': booking.transport_type, 'sales_order_type': booking.sales_order_type},
                   fields=['name', 'service_name', 'sequence'], order_by='sequence asc, name asc')
    services = {row.services: row for row in selected if row.applicable}
    details = {name: validate_binding('Service Type', name, booking.company) for name in services}
    for name, row in services.items():
        if row.service_name != details[name].name1:
            frappe.throw(_('Cargo service label differs from its stored service reference.'))
    if not rows and services:
        frappe.throw(_('No Cargo job sequence is configured for this Company, mode and movement.'))
    exact = set(services) & {row.service_name for row in rows}
    output, seen, sequence_numbers = [], set(), set()
    for row in rows:
        candidate = services.get(row.service_name)
        if candidate is None:
            configured = validate_binding('Service Type', row.service_name, booking.company)
            matches = [services[name] for name, detail in details.items() if name not in exact
                and (detail.name1, detail.transport_mode or '', detail.job_type) == (configured.name1, configured.transport_mode or '', configured.job_type)]
            if len(matches)>1:
                frappe.throw(_('Explicit Cargo service references have ambiguous sequence bindings.'))
            candidate = matches[0] if matches else None
        if candidate is None:
            continue
        if candidate.services in seen or row.sequence in sequence_numbers:
            frappe.throw(_('Cargo job sequence contains duplicate services or positions.'))
        seen.add(candidate.services)
        sequence_numbers.add(row.sequence)
        validate_binding('Service Type', row.service_name, booking.company)
        output.append(candidate)
    if set(services) - seen:
        frappe.throw(_('Selected Cargo services are missing from the Company job sequence.'))
    return output


def train_company(train):
    companies = set()
    for field in ('middle_mile', 'middle_mile_in_loading', 'middle_mile_copy'):
        for row in train.get(field, []):
            freight = row.get('fo') or (frappe.db.get_value('FPL Containers', row.container, 'freight_order_id') if row.get('container') else None)
            if freight:
                companies.add(freight_company(freight))
    if train.get('company'):
        companies.add(train.company)
    if len(companies) != 1:
        frappe.throw(_('A Cargo train must resolve to exactly one Company from its Bookings.'))
    return next(iter(companies))
