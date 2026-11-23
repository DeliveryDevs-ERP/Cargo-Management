"""Narrow Cargo Company isolation layered over native v16 role permissions."""
import frappe

BOOKING_FIELDS = {'FPL Freight Orders': 'sales_order_number', 'FPLRoadJob': 'sales_order_number',
    'FPLRailJob': 'sales_order_number', 'FPLYardJob': 'sales_order_number', 'FPLCrossStuffJob': 'sales_order_number',
    'FPL Containers': 'booking_order_id', 'Container or Vehicle Request': 'booking_order_id',
    'Perform Cross Stuff': 'booking_order_id'}
COMPANY_FIELDS = {'Booking Order', 'Service Type', 'FPL Jobs Sequence', 'FPL Cost Type',
                  'Rail Freight Cost', 'FPL Perform Middle Mile', 'Cargo Cross Stuff Transfer'}

TRAIN_ALLOCATIONS = '''(SELECT parent,parenttype,container FROM `tabFPL MM cdt`
    UNION ALL SELECT parent,parenttype,container FROM `tabNew MM cdt`)'''


def legacy_train_company(name):
    """Resolve an optional legacy Company from saved identities, never a label."""
    rows=frappe.db.sql(f'''SELECT DISTINCT booking.company FROM {TRAIN_ALLOCATIONS} allocation
        LEFT JOIN `tabFPL Containers` container ON container.name=allocation.container
        LEFT JOIN `tabFPL Freight Orders` freight ON freight.name=container.freight_order_id
        LEFT JOIN `tabBooking Order` booking ON booking.name=freight.sales_order_number
        WHERE allocation.parent=%s AND allocation.parenttype='FPL Perform Middle Mile'
          AND COALESCE(allocation.container,'')<>'' ''',name)
    companies={row[0] for row in rows}
    return next(iter(companies)) if len(companies)==1 and None not in companies and '' not in companies else None


def allowed_companies(user=None, doctype=None):
    user = user or frappe.session.user
    if user == 'Administrator':
        return None
    rows = frappe.get_all('User Permission', filters={'user': user, 'allow': 'Company'},
                          fields=['for_value', 'applicable_for', 'apply_to_all_doctypes'])
    return {row.for_value for row in rows if row.apply_to_all_doctypes or not row.applicable_for
            or row.applicable_for in (doctype, 'Booking Order')} or None


def has_permission(doc, user=None, ptype=None):
    allowed = allowed_companies(user, doc.doctype)
    if allowed is None:
        return True
    company = doc.get('company')
    # Saved authority comes from the database, not a supplied document payload.
    if doc.name and frappe.db.exists(doc.doctype,doc.name):
        if doc.doctype in BOOKING_FIELDS:
            persisted_booking=frappe.db.get_value(doc.doctype,doc.name,BOOKING_FIELDS[doc.doctype])
            persisted_company=frappe.db.get_value('Booking Order',persisted_booking,'company') if persisted_booking else None
        else:
            persisted_company=frappe.db.get_value(doc.doctype,doc.name,'company')
            if doc.doctype=='FPL Perform Middle Mile' and not persisted_company:
                persisted_company=legacy_train_company(doc.name)
                company=company or persisted_company
        shared=doc.doctype in ('Service Type','FPL Jobs Sequence','FPL Cost Type','Rail Freight Cost')
        if persisted_company not in allowed and not (shared and not persisted_company):
            return False
    if doc.doctype in BOOKING_FIELDS:
        booking = doc.get(BOOKING_FIELDS[doc.doctype])
        company = frappe.db.get_value('Booking Order', booking, 'company') if booking else None
    shared = doc.doctype in ('Service Type', 'FPL Jobs Sequence', 'FPL Cost Type', 'Rail Freight Cost')
    if not company and shared:
        return ptype not in ('write','create','delete','submit','cancel')
    return company in allowed


def query_condition(doctype, user=None):
    allowed = allowed_companies(user, doctype)
    if allowed is None:
        return ''
    companies = ','.join(frappe.db.escape(name) for name in sorted(allowed))
    table = '`tab' + doctype + '`'
    if doctype in BOOKING_FIELDS:
        return f'EXISTS (SELECT 1 FROM `tabBooking Order` cargo_scope WHERE cargo_scope.name={table}.`{BOOKING_FIELDS[doctype]}` AND cargo_scope.company IN ({companies}))'
    if doctype in COMPANY_FIELDS:
        if doctype=='FPL Perform Middle Mile':
            legacy=f'''EXISTS (SELECT 1 FROM {TRAIN_ALLOCATIONS} allocation
                LEFT JOIN `tabFPL Containers` container ON container.name=allocation.container
                LEFT JOIN `tabFPL Freight Orders` freight ON freight.name=container.freight_order_id
                LEFT JOIN `tabBooking Order` booking ON booking.name=freight.sales_order_number
                WHERE allocation.parent={table}.name AND allocation.parenttype='FPL Perform Middle Mile'
                  AND COALESCE(allocation.container,'')<>''
                HAVING COUNT(*)>0 AND COUNT(DISTINCT COALESCE(booking.company,''))=1 AND MIN(booking.company) IN ({companies}))'''
            return f"({table}.company IN ({companies}) OR (COALESCE({table}.company,'')='' AND {legacy}))"
        shared = doctype in ('Service Type', 'FPL Jobs Sequence', 'FPL Cost Type', 'Rail Freight Cost')
        return f'({table}.company IN ({companies})' + (f' OR COALESCE({table}.company,\'\')=\'\')' if shared else ')')
    return ''


def validate_expense_history(doc, method=None):
    # Use a current locking read, including child expenses. A previously loaded
    # document must not clear a retirement performed by another transaction.
    old = None
    if not doc.is_new():
        old = frappe.get_doc(doc.doctype, doc.name, for_update=True)
        if old.get('cargo_retired'):
            frappe.throw('Retired Cargo work is retained for financial traceability and cannot be processed again.')
        for field in ('cargo_retired', 'cargo_transfer', 'freight_order_id', 'sales_order_number', 'booking_order_id', 'company'):
            if doc.meta.has_field(field) and (doc.get(field) or None) != (old.get(field) or None):
                if field=='company' and doc.doctype=='FPL Perform Middle Mile' and not old.company and doc.company==legacy_train_company(doc.name):
                    continue
                frappe.throw('Saved Cargo ownership and transfer history cannot be rewritten: ' + field)
    elif doc.get('cargo_transfer'):
        if doc.cargo_transfer != frappe.flags.get('cargo_active_transfer'):
            frappe.throw('Replacement jobs require the active server-owned Cross-Stuff transfer.')
    if doc.get('cargo_retired'):
        frappe.throw('Retired Cargo work is retained for financial traceability and cannot be processed again.')
    current = {row.name: row for row in (doc.get('expenses') or [])}
    old_rows={row.name:row for row in (old.get('expenses') or [])} if old else {}
    provenance_fields = ('cargo_invoice_history', 'cargo_charge_key', 'cargo_tariff')
    for row in current.values():
        prior=old_rows.get(row.name)
        if not prior and row.name and frappe.db.get_value('Expenses cdt', row.name, 'name', for_update=True):
            frappe.throw('An existing Cargo expense identity cannot be reused under another parent.')
        for field in ('purchase_invoice_no','sales_invoice_no','purchase_invoiced_created'):
            if (row.get(field) or None)!=(prior.get(field) or None if prior else None):
                frappe.throw('Cargo invoice references are maintained by their native invoice/expense operation, not editable input.')
        # Hidden/read-only fields are still accepted in native document payloads.
        # Only the server's claim/charge operations may establish this provenance.
        for field in provenance_fields:
            if (row.get(field) or None) != (prior.get(field) or None if prior else None):
                frappe.throw('Cargo server-owned expense history cannot be supplied or rewritten: ' + field)
        if prior and prior.sales_invoice_no and frappe.utils.cint(row.invoiced_) != frappe.utils.cint(prior.invoiced_):
            frappe.throw('Cargo billability cannot change while a native Sales Invoice claim is active.')
    for previous in (old.get('expenses') or []) if old else []:
        if previous.name not in current and any(previous.get(field) for field in provenance_fields):
            frappe.throw('Cargo expense rows with server-owned history cannot be removed or replaced.')
        if not (previous.purchase_invoice_no or previous.sales_invoice_no):
            continue
        row = current.get(previous.name)
        if not row or any(row.get(key) != previous.get(key) for key in
            ('expense_type', 'amount', 'client', 'container_number', 'purchase_invoice_no', 'sales_invoice_no')):
            frappe.throw('A financially referenced Cargo expense cannot be removed, moved or rewritten.')
    from cargo_management.expense_controls import initialize_fixed_costs
    initialize_fixed_costs(doc)
    from cargo_management.cargo_management.api.expense_billing import expense_context
    for row in doc.get('expenses') or []:
        if row.expense_type:
            expense_context(doc, row)


def protect_job_deletion(doc, method=None):
    if not doc.is_new():
        doc = frappe.get_doc(doc.doctype, doc.name, for_update=True)
    if (doc.doctype == 'FPLCrossStuffJob' and not doc.get('expenses')
            and doc.get('performance_details') == frappe.flags.get('cargo_reversing_crossstuff')
            and doc.get('performance_details')):
        return  # Exact unchanged, cost-free job created by this journal only.
    if doc.get('cargo_retired') or doc.get('expenses') or doc.get('status') in ('Completed', 'In Progress'):
        frappe.throw('Cargo work with financial history or progress cannot be deleted.')


def protect_freight_deletion(doc, method=None):
    for kind in ('FPLRoadJob', 'FPLRailJob', 'FPLYardJob', 'FPLCrossStuffJob'):
        for name in frappe.get_all(kind, filters={'freight_order_id':doc.name}, pluck='name'):
            protect_job_deletion(frappe.get_doc(kind, name))


def validate_container_identity(doc, method=None):
    old=doc.get_doc_before_save()
    if old and any(doc.get(key)!=old.get(key) for key in ('freight_order_id','booking_order_id')):
        frappe.throw('An existing Cargo allocation cannot be reassigned to another Freight Order or Booking.')
    freight=frappe.get_doc('FPL Freight Orders',doc.freight_order_id)
    freight.check_permission('write')
    if freight.sales_order_number!=doc.booking_order_id:
        frappe.throw('Cargo allocation Booking/Freight Order lineage is inconsistent.')


def query_0(user=None):
    return query_condition('Booking Order', user)


def query_1(user=None):
    return query_condition('FPL Freight Orders', user)


def query_2(user=None):
    return query_condition('FPLRoadJob', user)


def query_3(user=None):
    return query_condition('FPLRailJob', user)


def query_4(user=None):
    return query_condition('FPLYardJob', user)


def query_5(user=None):
    return query_condition('FPLCrossStuffJob', user)


def query_6(user=None):
    return query_condition('FPL Containers', user)


def query_7(user=None):
    return query_condition('Container or Vehicle Request', user)


def query_8(user=None):
    return query_condition('Perform Cross Stuff', user)


def query_9(user=None):
    return query_condition('Service Type', user)


def query_10(user=None):
    return query_condition('FPL Jobs Sequence', user)


def query_11(user=None):
    return query_condition('FPL Cost Type', user)


def query_12(user=None):
    return query_condition('Rail Freight Cost', user)


def query_13(user=None):
    return query_condition('FPL Perform Middle Mile', user)


def query_14(user=None):
    return query_condition('Cargo Cross Stuff Transfer', user)
