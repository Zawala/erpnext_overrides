"""/launcher: one tile per app the user can open, plus the ERPNext desk.

A self-contained soft-UI page (launcher.html) with the system logo and the user's desk
theme. A tile shows only when that app's own page would let the user in, so nobody sees a
tile that ends in "Not Permitted".
"""
import frappe
from frappe import _
from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo

no_cache = 1

ICON = "/assets/erp_overrides/manifest/favicon-196.png"


def brand_logo():
	"""The site's own logo (Navbar / Website Settings), or this app's icon instead of Frappe's default."""
	logo = get_app_logo()
	return ICON if not logo or "frappe-framework-logo" in logo else logo


def _can_sales(user):
	from erp_overrides.api.sales import CHAIN_DOCTYPES

	return any(frappe.has_permission(dt, "read", user=user) for dt in CHAIN_DOCTYPES)


def _can_hr(user):
	from erp_overrides.api.hr import is_approver, is_hr

	return is_hr(user) or is_approver(user)


def _can_self_service(user):
	# Frappe HR's /hrms works off the Employee linked to the user; without one it has nothing to show
	return bool(frappe.db.exists("Employee", {"user_id": user, "status": ["!=", "Left"]}))


def _has_reviews(user):
	from erp_overrides.api.reviews import has_reports, has_reviews

	return has_reviews(user) or has_reports(user)


def _can_accounts(user):
	from erp_overrides.api.accounts import can_view, custodian_boxes

	return can_view(user) or bool(custodian_boxes(user))


def _can_admin(user):
	from erp_overrides.api.sysadmin import is_system_manager

	return is_system_manager(user)


# route, title, what it's for, icon (an inline SVG in launcher.html), who sees it
APPS = (
	("/sales", "Sales", "Leads, quotes and orders", "sales", _can_sales),
	("/hrms-admin", "HR", "Leave, expenses and payroll", "hr", _can_hr),
	("/hrms", "My HR", "Leave, check-in, expenses and payslips", "employee", _can_self_service),
	("/hrms-admin/calendar", "Who's off", "Who is on leave and who is in", "calendar", _can_self_service),
	("/hrms-admin/my-reviews", "My reviews", "Your bi-weekly check-ins, and your team's", "reviews", _has_reviews),
	("/accounts", "Accounts", "Banks, money owed and cash", "accounts", _can_accounts),
	("/sys-admin", "Admin", "Users, permissions and prices", "admin", _can_admin),
)


def _tiles(user):
	return [dict(route=r, title=_(t), hint=_(h), icon=i) for r, t, h, i, can in APPS if can(user)]


def home_page(user):
	"""Where a user lands after login: here, when there is at least one tile for them.
	Anyone else (a customer, a supplier) keeps Frappe's own home page."""
	if not user or user == "Guest":
		return None
	if frappe.get_cached_value("User", user, "user_type") == "System User" or _tiles(user):
		return "launcher"
	return None


def has_app_permission():
	return bool(home_page(frappe.session.user))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/launcher"
		raise frappe.Redirect(302)

	user = frappe.session.user
	tiles = _tiles(user)
	if frappe.get_cached_value("User", user, "user_type") == "System User":
		tiles.append(dict(route="/desk", title=_("Desk"), hint=_("Everything in ERPNext"), icon="desk",
		                  logo=frappe.get_hooks("app_logo_url", app_name="erpnext")[0]
		                  if "erpnext" in frappe.get_installed_apps() else None))

	full_name = frappe.utils.get_fullname(user)
	context.csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosempgrep: keep the new CSRF token
	context.no_breadcrumbs = True
	context.tiles = tiles
	context.full_name = full_name
	context.initials = "".join(w[0] for w in full_name.split()[:2]).upper() if full_name else "?"
	context.user_image = frappe.get_cached_value("User", user, "user_image")
	context.brand_logo = brand_logo()
	context.favicon = frappe.db.get_single_value("Website Settings", "favicon") or ICON
	context.desk_theme = (frappe.get_cached_value("User", user, "desk_theme") or "Light").lower()
	return context
