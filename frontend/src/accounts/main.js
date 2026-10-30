import { createApp } from "vue"
import { setConfig, frappeRequest, resourcesPlugin, Button, FeatherIcon } from "frappe-ui"

import App from "./App.vue"
import router from "./router"
import { boot } from "@/boot"
import "@/main.css"

setConfig("resourceFetcher", frappeRequest)

const app = createApp(App)
app.use(resourcesPlugin)
app.use(router)
app.component("Button", Button)
app.component("FeatherIcon", FeatherIcon)

async function start() {
	if (import.meta.env.DEV) {
		// the dev server serves accounts.html raw, so boot data comes from the API instead of Jinja
		try {
			const values = await frappeRequest({ url: "/api/method/erp_overrides.www.accounts.get_context_for_dev" })
			window.frappe = window.frappe || {}
			window.frappe.boot = values
		} catch (e) {
			window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`
			return
		}
	}
	Object.assign(boot, window.frappe?.boot || {})
	await router.isReady()
	app.mount("#app")

	if ("serviceWorker" in navigator && !import.meta.env.DEV) {
		navigator.serviceWorker
			.register("/assets/erp_overrides/accounts/sw.js", { type: "classic" })
			.catch((err) => console.error("Service worker registration failed", err))
	}
}

start()
