import frappe
from cargo_management.cargo_management.utils.search import search_arguments, results


@frappe.whitelist()
def get_applicable_containers(*args, **kwargs):
    arguments=search_arguments(args,kwargs)
    excluded=arguments.filters.get('not_in_container_number') or []
    if isinstance(excluded,str): excluded=[value.strip() for value in excluded.split(',') if value.strip()]
    sql="""SELECT DISTINCT container.name,container.container_number
        FROM `tabFPL Containers` container
        JOIN `tabFPLRoadJob` road_job ON container.freight_order_id=road_job.freight_order_id
        JOIN `tabContainer Type` type ON container.container_type=type.name
        WHERE container.container_location=road_job.job_start_location
          AND road_job.job_start_location=%s AND type.size=20 AND road_job.status='Assigned'"""
    parameters=[arguments.filters.get('job_start_location')]
    if excluded:
        sql+=' AND container.container_number NOT IN %s';parameters.append(tuple(excluded))
    if arguments.txt:
        sql+=' AND (container.container_number LIKE %s OR container.name=%s)';parameters.extend(('%'+arguments.txt+'%', arguments.txt))
    sql+=' ORDER BY container.container_number,container.name'
    return results(sql,parameters,'FPL Containers',arguments)
