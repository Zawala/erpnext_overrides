import { call, toast } from "frappe-ui"
import { errorMessages } from "@/utils/api"
import { boot } from "@/boot"

export const hr = (method, params) => call(`erp_overrides.api.hr.${method}`, params)
export const pay = (method, params) => call(`erp_overrides.api.pay_setup.${method}`, params)

export const isHR = () => !!boot.is_hr
// Payslip previews open on the format employees download in /hrms and get by email (Payroll Settings)
export const payslipPrint = () => ({ presetFormat: boot.payslip_format || "Standard", title: "Payslip as the employee sees it" })
export const can = (doctype, ptype = "read") => boot.permissions?.[doctype]?.[ptype] ?? false
export const deskUrl = (doctype, name) => `/app/${doctype.toLowerCase().replace(/ /g, "-")}${name ? `/${encodeURIComponent(name)}` : ""}`

export function ok(title, text) {
	toast({ title, text, icon: "check", iconClasses: "text-green-600" })
}

export function fail(e, title = "That didn't work") {
	toast({ title, text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600", timeout: 10 })
}

export { errorMessages }
