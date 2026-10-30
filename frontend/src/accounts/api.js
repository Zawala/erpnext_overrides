import { call, toast } from "frappe-ui"
import { errorMessages } from "@/utils/api"
import { boot } from "@/boot"

export const acc = (method, params) => call(`erp_overrides.api.accounts.${method}`, params)

export const canPost = () => !!boot.can_post
export const deskUrl = (doctype, name) => `/desk/${doctype.toLowerCase().replace(/ /g, "-")}${name ? `/${encodeURIComponent(name)}` : ""}`

/** Money in a given currency; ZWG isn't in every browser's currency list, so it is spelled out. */
export function cur(value, currency) {
	const n = Number(value || 0)
	const text = n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
	return `${currency || boot.currency || "USD"} ${text}`
}

export function ok(title, text) {
	toast({ title, text, icon: "check", iconClasses: "text-green-600" })
}

export function fail(e, title = "That didn't work") {
	toast({ title, text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600", timeout: 10 })
}

export { errorMessages }
