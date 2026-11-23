def execute(filters=None):
    from cargo_management.cargo_management.utils.reporting import execute_report
    return execute_report('Query report', filters)
