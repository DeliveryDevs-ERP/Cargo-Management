import frappe
from cargo_management.cargo_management.utils.search import search_arguments, require_read, results


@frappe.whitelist()
def get_applicable_jobs(doctype,txt,searchfield,start,page_len,filters):
    arguments=search_arguments((doctype,txt,searchfield,start,page_len,filters),{})
    excluded=arguments.filters.get('not_in_container') or []
    if isinstance(excluded,str): excluded=frappe.parse_json(excluded)
    sql="""SELECT DISTINCT container.name,container.container_number,freight_order.size
        FROM `tabFPL Containers` container
        JOIN `tabFPL Freight Orders` freight_order ON container.freight_order_id=freight_order.name
        JOIN `tabFPL Jobs` jobs ON jobs.parent=freight_order.name
        JOIN `tabService Type` service ON service.name=jobs.job_name
        WHERE freight_order.last_job='Gate In' AND freight_order.next_job='Gate Out'
          AND service.name1='Middle Mile' AND freight_order.mm_completed_=0
          AND jobs.start_location=%s AND jobs.end_location=%s"""
    parameters=[arguments.filters.get('container_location'),arguments.filters.get('container_next_location')]
    if arguments.txt:
        sql+=' AND (container.container_number LIKE %s OR container.name=%s)';parameters.extend(('%'+arguments.txt+'%', arguments.txt))
    if excluded:
        sql+=' AND container.name NOT IN %s';parameters.append(tuple(excluded))
    sql+=' ORDER BY container.container_number,freight_order.size,container.name'
    return results(sql,parameters,'FPL Containers',arguments)


@frappe.whitelist()
def get_containers_from_Loading(*args,**kwargs):
    arguments=search_arguments(args,kwargs)
    parent=arguments.filters.get('parent')
    require_read('FPL Perform Middle Mile',parent)
    return results("""SELECT DISTINCT loading.container,loading.container_number
        FROM `tabFPL MM cdt` loading
        WHERE loading.container IS NOT NULL AND loading.container<>''
          AND loading.parentfield='middle_mile' AND loading.parent=%s
          AND (loading.container_number LIKE %s OR loading.container=%s) ORDER BY loading.container_number,loading.container""",
        (parent,'%'+arguments.txt+'%',arguments.txt),'FPL Containers',arguments)


@frappe.whitelist()
def fetch_wagons_from_undeparted_trains(departure_location, movement_type):
    require_read("FPL Perform Middle Mile")
    query = """
        SELECT 
            D.wagon_number,
            D.container,
            D.container_number,
            D.weight,
            D.size,
            D.parent,
            W.wagon_type
        FROM 
            `tabFPL MM cdt` D
        LEFT JOIN 
            `tabFPL Wagon cdt` W ON D.wagon_number = W.wagon_number AND W.parent = D.parent
        LEFT JOIN 
            `tabFPL Perform Middle Mile` PM ON PM.name = D.parent
        WHERE 
            D.parentfield = 'middle_mile_in_loading'
            AND D.loaded_ = 1
            AND D.departed_ = 0
            AND PM.departure_location = %s
            AND PM.movement_type = %s
            AND D.wagon_number NOT IN (
                SELECT DISTINCT A.wagon_number
                FROM (
                    SELECT 
                        wagon_number,
                        creation,
                        departed_,
                        ROW_NUMBER() OVER (PARTITION BY wagon_number ORDER BY creation DESC) AS rn
                    FROM `tabFPL MM cdt`
                ) A
                WHERE A.rn = 1 AND A.departed_ = 1
            )
    """
    wagons = frappe.db.sql(query, (departure_location, movement_type), as_dict=True)
    return [row for row in wagons if frappe.has_permission('FPL Perform Middle Mile','read',doc=row.parent)]

@frappe.whitelist()
def get_wagons_from_train(train_number):
    require_read("FPL Perform Middle Mile",train_number)
    # SQL query to fetch wagons associated with a specified train number
    query = """
        SELECT
            wagons.wagon_number,
            wagons.wagon_type,
            wagons.loaded_
        FROM
            `tabFPL Wagon cdt` AS wagons
        WHERE
            wagons.parent = %s
    """
    wagons = frappe.db.sql(query, train_number, as_dict=True)
    return wagons
