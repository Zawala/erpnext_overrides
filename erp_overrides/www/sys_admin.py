import frappe
from frappe import _

from erp_overrides.api.sysadmin import is_system_manager
from erp_overrides.www.launcher import brand_logo

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.local.request.path
		raise frappe.Redirect(302)
	if not is_system_manager():
		frappe.throw(_("The admin app is for System Managers."), frappe.PermissionError)

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
	if not is_system_manager():
		frappe.throw(_("The admin app is for System Managers."), frappe.PermissionError)
	return get_boot()


def get_boot():
	user = frappe.session.user
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	return frappe._dict(
		site_name=frappe.local.site,
		user=user,
		full_name=frappe.utils.get_fullname(user),
		user_image=frappe.db.get_value("User", user, "user_image"),
		roles=frappe.get_roles(user),
		company=company,
		currency=company and frappe.get_cached_value("Company", company, "default_currency"),
		selling_price_list=frappe.db.get_single_value("Selling Settings", "selling_price_list"),
		buying_price_list=frappe.db.get_single_value("Buying Settings", "buying_price_list"),
		is_settings_manager=True,
		desk_url="/desk",
		app_logo=brand_logo(),
	)
