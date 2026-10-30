import { call, toast } from "frappe-ui"
import { errorMessages } from "@/utils/api"

export const adm = (method, params) => call(`erp_overrides.api.sysadmin.${method}`, params)

export const deskUrl = (doctype, name) => `/app/${doctype.toLowerCase().replace(/ /g, "-")}${name ? `/${encodeURIComponent(name)}` : ""}`

/** A file download from a whitelisted GET method (export, template). */
export function download(method, params) {
	const q = new URLSearchParams(
		Object.entries(params).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v ?? "")])
	)
	window.open(`/api/method/erp_overrides.api.sysadmin.${method}?${q}`, "_blank")
}

export function rate(value, currency) {
	if (value === null || value === undefined || value === "") return ""
	const n = Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
	return currency ? `${currency} ${n}` : n
}

export function ok(title, text) {
	toast({ title, text, icon: "check", iconClasses: "text-green-600" })
}

export function fail(e, title = "That didn't work") {
	toast({ title, text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600", timeout: 10 })
}

export const PTYPE_LABELS = {
	read: "Read", write: "Edit", create: "Create", submit: "Submit", cancel: "Cancel", delete: "Delete",
	export: "Export", import: "Import",
}
