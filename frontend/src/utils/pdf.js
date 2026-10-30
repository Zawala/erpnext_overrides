import { toast } from "frappe-ui"
import { API } from "./api"

/**
 * Fetch the PDF in the background so a server failure becomes a message, not a traceback page.
 * opts: { print_format, letterhead, no_letterhead }
 * Returns { blob } or { error }.
 */
export async function fetchPdf(doctype, name, opts = {}) {
	const params = new URLSearchParams({ doctype, name })
	for (const [k, v] of Object.entries(opts)) if (v !== null && v !== undefined) params.set(k, v)
	const res = await fetch(`/api/method/${API}.download_pdf?${params}`, {
		headers: { "X-Frappe-CSRF-Token": window.csrf_token },
	})
	if (!res.ok || !(res.headers.get("content-type") || "").includes("pdf")) return { error: await pdfError(res) }
	return { blob: await res.blob() }
}

export async function downloadPdf(doctype, name, opts = {}, filename = `${name}.pdf`) {
	const { blob, error } = await fetchPdf(doctype, name, opts)
	if (error) {
		toast({ title: "Could not create the PDF", text: error, icon: "alert-circle", iconClasses: "text-red-600", timeout: 10 })
		return
	}
	const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: filename })
	document.body.appendChild(a)
	a.click()
	a.remove()
	setTimeout(() => URL.revokeObjectURL(a.href), 10000)
}

async function pdfError(res) {
	let body = {}
	try {
		body = await res.json()
	} catch {
		return `Server returned ${res.status}`
	}
	const exc = String(body.exception || body.exc || "")
	if (/No wkhtmltopdf executable/i.test(exc)) {
		return "PDF printing isn't set up on this server (wkhtmltopdf is missing). Ask your administrator."
	}
	try {
		const msgs = JSON.parse(body._server_messages || "[]").map((m) => JSON.parse(m).message)
		if (msgs.length) return msgs.map((m) => String(m).replace(/<[^>]+>/g, "")).join(" ")
	} catch {}
	return exc.split("\n").filter(Boolean).pop() || `Server returned ${res.status}`
}
