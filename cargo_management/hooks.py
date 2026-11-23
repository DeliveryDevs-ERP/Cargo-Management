app_name = "cargo_management"
app_title = "Frappe Cargo Management"
app_publisher = "Osama"
app_description = "Cargo management app "
app_email = "osama.ahmed@deliverydevs.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cargo_management",
# 		"logo": "/assets/cargo_management/logo.png",
# 		"title": "Frappe Cargo Management",
# 		"route": "/cargo_management",
# 		"has_permission": "cargo_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cargo_management/css/cargo_management.css"
# app_include_js = "/assets/cargo_management/js/cargo_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/cargo_management/css/cargo_management.css"
# web_include_js = "/assets/cargo_management/js/cargo_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cargo_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {"Sales Invoice": "public/js/sales_invoice.js", **{name: "public/js/cargo_expense_actions.js" for name in
    ("FPLRoadJob","FPLYardJob","Perform Cross Stuff","FPL Perform Middle Mile")}}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cargo_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "cargo_management.utils.jinja_methods",
# 	"filters": "cargo_management.utils.jinja_filters"
# }

jinja = {
	"methods": [
        "cargo_management.cargo_management.utils.jinja.get_qr_code",
        "cargo_management.print_context.get_cargo_print_context"
    ],
	# "filters": "rental_management.utils.jinja_filters
}


# Installation
# ------------

before_install = "cargo_management.cargo_management.install.before_install"
before_migrate = "cargo_management.setup.ensure_cargo_roles"
after_install = "cargo_management.cargo_management.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cargo_management.uninstall.before_uninstall"
# after_uninstall = "cargo_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cargo_management.utils.before_app_install"
# after_app_install = "cargo_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cargo_management.utils.before_app_uninstall"
# after_app_uninstall = "cargo_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cargo_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "FPL Containers": {"before_validate": "cargo_management.permissions.validate_container_identity"},
    "FPL Freight Orders": {"on_trash": "cargo_management.permissions.protect_freight_deletion"},
    "Service Type": {"on_update": "cargo_management.workspace.reconcile", "after_delete": "cargo_management.workspace.reconcile"},
    "Sales Invoice": {
        "validate": "cargo_management.cargo_management.api.expense_billing.validate_cargo_invoice",
        "before_submit": "cargo_management.cargo_management.api.expense_billing.before_submit",
        "on_submit": "cargo_management.cargo_management.api.Sales_inv_validation_overload.update_expense_references",
        "before_cancel": "cargo_management.cargo_management.api.expense_billing.before_cancel",
        "on_cancel": "cargo_management.cargo_management.api.expense_billing.release_cancelled_invoice"
    },
    "Sales Order": {
        "on_trash": "cargo_management.cargo_management.doctype.booking_order.booking_order.check_booking_order_status"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"cargo_management.tasks.all"
# 	],
# 	"daily": [
# 		"cargo_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"cargo_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cargo_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cargo_management.tasks.monthly"
# 	],
# }

scheduler_events = {
    "cron": {
        "*/6 * * * *": [
            "cargo_management.tasks.crypto.pull_and_store",
        ],
    },
}


# Testing
# -------

# before_tests = "cargo_management.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cargo_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "cargo_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cargo_management.utils.before_request"]
# after_request = ["cargo_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["cargo_management.utils.before_job"]
# after_job = ["cargo_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"cargo_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


# Reconcile only Cargo-owned schema and the explicitly opt-in external job.
after_sync = "cargo_management.setup.reconcile"
after_migrate = "cargo_management.setup.reconcile"
# Native DocPerm checks still apply. These hooks add the Company restriction
# missing from legacy Data references; no ERPNext standard grants are replaced.
_cargo_scoped_types = ["Booking Order", "FPL Freight Orders", "FPLRoadJob", "FPLRailJob", "FPLYardJob",
    "FPLCrossStuffJob", "FPL Containers", "Container or Vehicle Request", "Perform Cross Stuff",
    "Service Type", "FPL Jobs Sequence", "FPL Cost Type", "Rail Freight Cost", "FPL Perform Middle Mile",
    "Cargo Cross Stuff Transfer"]
has_permission = {name: "cargo_management.permissions.has_permission" for name in _cargo_scoped_types}
permission_query_conditions = {name: "cargo_management.permissions.query_" + str(index)
    for index, name in enumerate(_cargo_scoped_types)}
for _name in ("FPLRoadJob", "FPLYardJob", "FPLRailJob", "FPLCrossStuffJob"):
    doc_events.setdefault(_name, {}).update({"before_validate": "cargo_management.permissions.validate_expense_history",
                                          "on_trash": "cargo_management.permissions.protect_job_deletion"})
for _name in ("Perform Cross Stuff", "FPL Perform Middle Mile"):
    doc_events.setdefault(_name, {})["before_validate"] = "cargo_management.permissions.validate_expense_history"
doc_events.setdefault('Location', {})['validate'] = 'cargo_management.location.validate_location'
extend_doctype_class = {name: ["cargo_management.expense_controls.CargoExpenseControls"] for name in
    ("FPLRoadJob", "FPLYardJob", "Perform Cross Stuff", "FPL Perform Middle Mile")}
extend_doctype_class['Notification'] = ['cargo_management.notifications.CargoNotificationRecipients']
app_home = "/desk/cargo-management"
add_to_apps_screen = [{"name": app_name, "title": app_title, "route": app_home,
    "logo": "/assets/cargo_management/images/cargo-management-logo.webp",
    "has_permission": "cargo_management.setup.has_app_permission"}]

# Preserve the local outbound opt-out independently of financial operations.
before_request = ["cargo_management.outbound_safety.install"]
before_job = ["cargo_management.outbound_safety.before_job"]
extend_doctype_class.setdefault('Scheduled Job Type', []).append(
    'cargo_management.outbound_safety.OutboundScheduledJobs')
