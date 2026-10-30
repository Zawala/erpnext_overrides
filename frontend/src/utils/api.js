import { call } from "frappe-ui"

export const API = "erp_overrides.api.sales"
export const api = (method, params) => call(`${API}.${method}`, params)

/** Server messages from a failed call, as plain text, verbatim — the manual quotes them word for word. */
export function errorMessages(e) {
	const strip = (s) => String(s).replace(/<[^>]+>/g, "").trim()
	let msgs = (e?.messages || []).map(strip).filter(Boolean)
	if (!msgs.length && e?.message) msgs = [strip(e.message)]
	return msgs.length ? msgs : ["Something went wrong"]
}
