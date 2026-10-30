import { boot } from "@/boot"

export function money(value, currency) {
	const cur = currency || boot.currency || "USD"
	const n = Number(value || 0)
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: 2 }).format(n)
	} catch {
		return `${cur} ${n.toFixed(2)}`
	}
}

export function compactMoney(value, currency) {
	const cur = currency || boot.currency || "USD"
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0))
	} catch {
		return money(value, cur)
	}
}

export function date(value) {
	if (!value) return ""
	const d = new Date(String(value).slice(0, 10) + "T00:00:00")
	return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

export function relative(value) {
	if (!value) return ""
	const diff = (Date.now() - new Date(String(value).replace(" ", "T")).getTime()) / 1000
	if (diff < 60) return "just now"
	if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
	if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
	if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`
	return date(value)
}

export const today = () => new Date().toISOString().slice(0, 10)

export function addDays(iso, days) {
	const d = new Date((iso || today()) + "T00:00:00")
	d.setDate(d.getDate() + days)
	return d.toISOString().slice(0, 10)
}

const STATUS_THEME = {
	green: ["Ordered", "Completed", "Converted", "Received", "To Bill", "Delivered",
		"Approved", "Paid", "Active", "Current", "Present"],
	blue: ["Open", "Replied", "To Deliver and Bill", "To Deliver", "To Receive and Bill", "To Receive", "Pending",
		"Partially Ordered", "Partially Received", "Quotation", "Opportunity", "Interested", "Submitted",
		"On Leave", "Work From Home"],
	orange: ["Draft", "On Hold", "Lead", "Unpaid", "Suspended", "Half Day", "Queued"],
	red: ["Lost", "Expired", "Cancelled", "Closed", "Lost Quotation", "Do Not Contact", "Stopped",
		"Rejected", "Left", "Absent", "Failed"],
}

export function statusTheme(status) {
	for (const [theme, list] of Object.entries(STATUS_THEME)) if (list.includes(status)) return theme
	return "gray"
}

export function docStatus(doc) {
	if (!doc) return ""
	if (doc.docstatus === 2) return "Cancelled"
	if (doc.docstatus === 0 && doc.__submittable) return "Draft"
	return doc.status || (doc.docstatus === 0 ? "Draft" : "Submitted")
}
