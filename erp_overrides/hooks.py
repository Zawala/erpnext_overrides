app_name = "erp_overrides"
app_title = "Erp Overrides"
app_publisher = "Kelvin Zawala"
app_description = "Mobile-first PWAs (sales, HR, accounts, admin) and their APIs on top of ERPNext"
app_email = "kelvinzawala@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# The app launcher, which is also where everyone lands after login (see get_website_user_home_page)
add_to_apps_screen = [
	{
		"name": "erp_overrides",
		"logo": "/assets/erp_overrides/manifest/favicon-196.png",
		"title": "Apps",
		"route": "/launcher",
		"has_permission": "erp_overrides.www.launcher.has_app_permission",
	}
]

# Land on /launcher after login instead of /desk; Frappe asks this for system users too
get_website_user_home_page = "erp_overrides.www.launcher.home_page"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erp_overrides/css/erp_overrides.css"
# app_include_js = "/assets/erp_overrides/js/erp_overrides.js"

# include js, css files in header of web template
# web_include_css = "/assets/erp_overrides/css/erp_overrides.css"
# web_include_js = "/assets/erp_overrides/js/erp_overrides.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erp_overrides/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# (the Quotation print guard's UI half is a Client Script, not an app asset —
#  see scripts/install_print_guard.py)
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "erp_overrides/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Sales PWA (frontend/) — every /sales/* path renders www/sales.html
website_route_rules = [
	{"from_route": "/sales/<path:app_path>", "to_route": "sales"},
	{"from_route": "/hrms-admin", "to_route": "hrms_admin"},
	{"from_route": "/hrms-admin/<path:app_path>", "to_route": "hrms_admin"},
	{"from_route": "/accounts", "to_route": "accounts"},
	{"from_route": "/accounts/<path:app_path>", "to_route": "accounts"},
	{"from_route": "/sys-admin", "to_route": "sys_admin"},
	{"from_route": "/sys-admin/<path:app_path>", "to_route": "sys_admin"},
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	# the Standard Payslip's figures (erp_overrides.payslip)
	"methods": ["erp_overrides.payslip.standard_payslip"],
}
# jinja = {
# 	"methods": "erp_overrides.utils.jinja_methods",
# 	"filters": "erp_overrides.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erp_overrides.install.before_install"
# Patches are marked done on a fresh install without running, so set-up that must exist runs here too
after_install = [
	"erp_overrides.payslip.install_standard_payslip",
	"erp_overrides.patches.v1_0.agreed_net_pay.execute",
]

# Uninstallation
# ------------

# before_uninstall = "erp_overrides.uninstall.before_uninstall"
# after_uninstall = "erp_overrides.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "erp_overrides.utils.before_app_install"
# after_app_install = "erp_overrides.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "erp_overrides.utils.before_app_uninstall"
# after_app_uninstall = "erp_overrides.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "erp_overrides.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erp_overrides.notifications.get_notification_config"

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

# a Quotation may only be printed once its workflow reaches an approved state
has_permission = {
	"Quotation": "erp_overrides.quotation.has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
	"Quotation": {
		"before_print": "erp_overrides.quotation.before_print",
	},
	"Employee": {
		# Fill an empty holiday list with "<company country> <year>".
		"validate": [
			"erp_overrides.hrms_setup.set_employee_holiday_list",
			# HR staff aren't limited to their own record (erp_overrides.hr_access)
			"erp_overrides.hr_access.keep_hr_unrestricted",
		],
	},
	# Hardware stock that looks after itself (erp_overrides.stock_light)
	"Item": {
		"before_validate": "erp_overrides.stock_light.item_before_validate",
	},
	"Sales Invoice": {
		"before_validate": "erp_overrides.stock_light.invoice_before_validate",
	},
	"Purchase Receipt": {
		"before_validate": "erp_overrides.stock_light.receipt_before_validate",
	},
	# three-way match before a supplier is paid (erp_overrides.three_way)
	"Payment Entry": {
		"before_submit": "erp_overrides.three_way.payment_before_submit",
	},
	"Purchase Order": {
		"before_validate": "erp_overrides.stock_light.fill_warehouses",
		"on_submit": "erp_overrides.stock_light.purchase_order_on_submit",
	},
	"Sales Order": {
		"before_validate": "erp_overrides.stock_light.fill_warehouses",
	},
	"Delivery Note": {
		"before_validate": "erp_overrides.stock_light.fill_warehouses",
	},
	"User": {
		"on_update": "erp_overrides.hr_access.lift_on_hr_role",
	},
	"Letter Head": {
		# private logos break every PDF printed by anyone but their uploader (payslip emails, …)
		"on_update": "erp_overrides.patches.v1_0.make_letterhead_logos_public.on_letter_head_update",
	},
	"Payroll Settings": {
		# Payslip format → Salary Slip's default print format (what /hrms downloads and emails attach)
		"validate": "erp_overrides.payslip.validate_payroll_settings",
		"on_update": "erp_overrides.payslip.sync_default_format",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"erp_overrides.tasks.all"
# 	],
# 	"daily": [
# 		"erp_overrides.tasks.daily"
# 	],
# 	"hourly": [
# 		"erp_overrides.tasks.hourly"
# 	],
# 	"weekly": [
# 		"erp_overrides.tasks.weekly"
# 	],
# 	"monthly": [
# 		"erp_overrides.tasks.monthly"
# 	],
# }

scheduler_events = {
	"cron": {
		# Tender feeds (stubs in erp_overrides.scrapers; see docs/sadc-data-feeds.md)
		"0 0,8,16 * * *": [
			"erp_overrides.scrapers.enqueue_get_tenders",
			"erp_overrides.scrapers.enqueue_get_zppa_portal_tenders",
		],
		# One email per country with the tenders the feeds brought in
		"30 0,8,16 * * *": [
			"erp_overrides.tender_digest.send_tender_digests",
		],
		# Central-bank rates into Currency Exchange, weekdays (stub in erp_overrides.scrapers)
		"0 11,17 * * 1-5": [
			"erp_overrides.scrapers.enqueue_sync_rates",
		],
		# Bi-weekly reviews: open windows, remind 2 days before due, mark overdue (erp_overrides.reviews)
		"0 6 * * *": [
			"erp_overrides.reviews.daily",
		],
		# ... and the overdue summary to HR, Monday mornings
		"0 7 * * 1": [
			"erp_overrides.reviews.weekly_overdue_summary",
		],
		# Keep this and next year's holiday lists and assignments loaded; on 1 Jan moves staff to the new year.
		"30 0 1 * *": [
			"erp_overrides.hrms_setup.roll_holiday_lists",
		],
	},
}

# Testing
# -------

# before_tests = "erp_overrides.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "erp_overrides.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erp_overrides.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erp_overrides.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# PDFs embed the site's own images instead of fetching them over HTTP (erp_overrides.pdf_images)
before_request = ["erp_overrides.pdf_images.install"]
# after_request = ["erp_overrides.utils.after_request"]

# Job Events
# ----------
before_job = ["erp_overrides.pdf_images.install"]
# after_job = ["erp_overrides.utils.after_job"]

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
# 	"erp_overrides.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

