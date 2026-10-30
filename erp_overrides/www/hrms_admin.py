import frappe
from frappe import _

from erp_overrides.api.app_settings import is_settings_manager
from erp_overrides.api.hr import HR_DOCTYPES, get_team, is_approver, is_hr
from erp_overrides.api.leave_calendar import can_view as can_view_calendar
from erp_overrides.api.reviews import has_reports, has_reviews
from erp_overrides.payslip import employee_format
from erp_overrides.www.launcher import brand_logo

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.local.request.path
		raise frappe.Redirect(302)
	# employees get in too, to Who's off and their reviews only (employee_only in the boot)
	if not (is_hr() or is_approver() or can_view_calendar()):
		frappe.throw(_("The HR admin app is for HR and approvers. Employees use /hrms."), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosempgrep
	context = frappe._dict()
	context.csrf_token = csrf_token
	context.boot = frappe.as_json(get_boot(), indent=None)
	context.site_name = frappe.local.site
	return context


@frappe.whitelist(methods=["POST"])
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	user = frappe.session.user
	roles = frappe.get_roles(user)
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	return frappe._dict(
		site_name=frappe.local.site,
		user=user,
		full_name=frappe.utils.get_fullname(user),
		user_image=frappe.db.get_value("User", user, "user_image"),
		roles=roles,
		company=company,
		currency=company and frappe.get_cached_value("Company", company, "default_currency"),
		is_hr=is_hr(user),
		# an employee who is neither HR nor an approver: Who's off and reviews only
		employee_only=not (is_hr(user) or is_approver(user)),
		# bi-weekly reviews (erp_overrides.reviews): their own, and their team's as a manager
		has_reviews=has_reviews(user),
		has_reports=has_reports(user),
		is_leave_approver="Leave Approver" in roles,
		is_expense_approver="Expense Approver" in roles,
		team=get_team(user),
		permissions={
			dt: {
				"read": bool(frappe.has_permission(dt, "read")),
				"create": bool(frappe.has_permission(dt, "create")),
			}
			for dt in HR_DOCTYPES
		},
		is_settings_manager=is_settings_manager("hr", user),
		payslip_format=employee_format(),
		desk_url="/desk",
		app_logo=brand_logo(),
	)
