import frappe
from cargo_management.cargo_management.utils.search import search_arguments, require_read, results


@frappe.whitelist()
def get_unique_service_types(*args, **kwargs):
    arguments=search_arguments(args,kwargs)
    require_read('Service Type')
    if arguments.filters.get('booking_order_id'):
        from cargo_management.cargo_management.utils.configuration import booking_company, catalog_filters
        company = booking_company(arguments.filters.booking_order_id, 'read')
        mode = frappe.db.get_value('Booking Order', arguments.filters.booking_order_id, 'transport_type')
        return frappe.get_list('Service Type', fields=['name', 'name1'],
            filters=catalog_filters('Service Type', company, {'transport_mode': mode}),
            or_filters=[['name1', 'like', '%' + arguments.txt + '%'], ['name', '=', arguments.txt]],
            order_by='name1, name', limit_start=arguments.start, limit_page_length=arguments.page_len, as_list=True)
    # v16 requires dict function syntax. Keep the original SQL MIN/name1
    # grouping and database collation while applying native permissions.
    return frappe.get_list('Service Type',fields=[{'MIN':'name','as':'name'},'name1'],
        or_filters=[['name1','like','%'+arguments.txt+'%'],['name','=',arguments.txt]],group_by='name1',order_by='name1',
        limit_start=arguments.start,limit_page_length=arguments.page_len,as_list=True)


def _containers(doctype,txt,searchfield,start,page_len,filters,prefix,status):
    arguments=search_arguments((doctype,txt,searchfield,start,page_len,filters),{})
    booking=arguments.filters.get('booking_order_id')
    if not booking: frappe.throw('Booking Order ID is required to fetch containers.')
    require_read('Booking Order',booking)
    return results("""SELECT container.name,container.container_number
        FROM `tabFPL Containers` container
        JOIN `tabFPL Freight Orders` freight_order ON container.freight_order_id=freight_order.name
        WHERE freight_order.sales_order_number=%s AND container.status=%s
          AND freight_order.name LIKE %s AND (container.container_number LIKE %s OR container.name=%s)
        ORDER BY container.container_number,container.name""",
        (booking,status,prefix+'-%','%'+arguments.txt+'%',arguments.txt),'FPL Containers',arguments)


@frappe.whitelist()
def get_FO_containers(doctype,txt,searchfield,start,page_len,filters):
    return _containers(doctype,txt,searchfield,start,page_len,filters,'FO','Filled')


@frappe.whitelist()
def get_CFO_containers(doctype,txt,searchfield,start,page_len,filters):
    return _containers(doctype,txt,searchfield,start,page_len,filters,'CFO','Empty')


@frappe.whitelist()
def get_BOs_name(doctype,txt,searchfield,start,page_len,filters):
    arguments=search_arguments((doctype,txt,searchfield,start,page_len,filters),{})
    require_read('Container or Vehicle Request')
    return results("""SELECT DISTINCT booking_order_id FROM `tabContainer or Vehicle Request`
        WHERE docstatus=1 AND (cross_stuff_performance IS NULL OR cross_stuff_performance='')
          AND booking_order_id LIKE %s ORDER BY booking_order_id""",
        ('%'+arguments.txt+'%',),'Booking Order',arguments)


@frappe.whitelist()
def get_Containers_for_CS_expenses(*args,**kwargs):
    arguments=search_arguments(args,kwargs)
    included=arguments.filters.get('in_container') or []
    if isinstance(included,str): included=frappe.parse_json(included)
    require_read('FPL Containers')
    if not included:
        return []
    sql='SELECT name,container_number FROM `tabFPL Containers` WHERE (container_number LIKE %s OR name=%s)'
    parameters=['%'+arguments.txt+'%',arguments.txt]
    if included:
        sql+=' AND name IN %s';parameters.append(tuple(included))
    sql+=' ORDER BY container_number,name'
    return results(sql,parameters,'FPL Containers',arguments)
