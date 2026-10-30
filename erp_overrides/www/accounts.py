import frappe
from frappe import _

from erp_overrides.api.app_settings import is_settings_manager
from erp_overrides.api.accounts import FINANCE_DOCTYPES, _bank_accounts, can_post, can_view, custodian_boxes, is_accounts_manager
from erp_overrides.www.launcher import brand_logo

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.local.request.path
		raise frappe.Redirect(302)
	if not can_view() and not custodian_boxes():
		frappe.throw(_("The accounts app is for the accounts team and managers."), frappe.PermissionError)

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
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	posts = can_post(user)
	return frappe._dict(
		site_name=frappe.local.site,
		user=user,
		full_name=frappe.utils.get_fullname(user),
		user_image=frappe.db.get_value("User", user, "user_image"),
		roles=frappe.get_roles(user),
		company=company,
		currency=company and frappe.get_cached_value("Company", company, "default_currency"),
		can_post=posts,
		read_only=not posts,
		# a petty cash custodian with no accounts or manager role sees only their box
		petty_boxes=custodian_boxes(user),
		petty_cash_only=not can_view(user),
		is_manager=is_accounts_manager(user),
		banks=_bank_accounts(company) if posts else [],
		cash_accounts=frappe.get_all("Account", filters={"company": company, "account_type": "Cash", "is_group": 0, "disabled": 0},
		                             fields=["name as account", "account_name", "account_currency as currency"]) if posts else [],
		permissions={
			dt: {"read": bool(frappe.has_permission(dt, "read")), "create": bool(frappe.has_permission(dt, "create"))}
			for dt in FINANCE_DOCTYPES
		},
		is_settings_manager=is_settings_manager("accounts", user),
		# the Documents pages price invoice lines from these, as the sales app does
		selling_price_list=frappe.db.get_single_value("Selling Settings", "selling_price_list"),
		buying_price_list=frappe.db.get_single_value("Buying Settings", "buying_price_list"),
		desk_url="/desk",
		app_logo=brand_logo(),
	)
