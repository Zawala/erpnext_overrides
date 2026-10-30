import { createRouter, createWebHistory } from "vue-router"
import { boot } from "@/boot"
import { records, canRead, canCreate } from "./records"

// Managers without an accounts role read Home and Dashboards; everything else posts or reconciles
const postOnly = { postOnly: true }

const routes = [
	{ path: "/", name: "Home", component: () => import("./pages/Home.vue") },
	{ path: "/bank", name: "Bank", component: () => import("./pages/Bank.vue"), meta: postOnly },
	{ path: "/bank/rules", name: "Rules", component: () => import("./pages/Rules.vue"), meta: postOnly },
	{ path: "/bank/upload", name: "Upload", component: () => import("./pages/Upload.vue"), meta: postOnly },
	{ path: "/bank/:account", name: "BankAccount", component: () => import("./pages/Bank.vue"), props: true, meta: postOnly },
	{ path: "/receivables", name: "Receivables", component: () => import("./pages/Ageing.vue"), props: { partyType: "Customer" }, meta: postOnly },
	{ path: "/payables", name: "Payables", component: () => import("./pages/Ageing.vue"), props: { partyType: "Supplier" }, meta: postOnly },
	{ path: "/payables/new-bill", name: "NewBill", component: () => import("./pages/NewBill.vue"), meta: postOnly },
	{ path: "/petty-cash", name: "PettyCash", component: () => import("./pages/PettyCash.vue"), meta: { pettyCash: true } },
	{ path: "/settings", name: "Settings", component: () => import("./pages/Settings.vue"), meta: { managerOnly: true } },
	{ path: "/payments", name: "Payments", component: () => import("./pages/Payments.vue"), meta: postOnly },
	{ path: "/dashboards", name: "Dashboards", component: () => import("./pages/Dashboards.vue") },
	{ path: "/rates", name: "Rates", component: () => import("./pages/Rates.vue"), meta: postOnly },
	{ path: "/reports", name: "Reports", component: () => import("./pages/Reports.vue") },
	// invoices, payments, journals, dunning and their templates (records.js)
	{ path: "/records/:slug", name: "Records", component: () => import("./pages/RecordList.vue"), props: true, meta: { ...postOnly, record: true } },
	{ path: "/records/:slug/new", name: "NewRecord", component: () => import("./pages/RecordForm.vue"), props: true, meta: { ...postOnly, record: "create" } },
	{ path: "/records/:slug/:name", name: "Record", component: () => import("./pages/RecordForm.vue"), props: true, meta: { ...postOnly, record: true } },
	{ path: "/:pathMatch(.*)*", redirect: "/" },
]

const router = createRouter({ history: createWebHistory("/accounts"), routes })

router.beforeEach((to) => {
	// a custodian with no accounts or manager role only keeps petty cash
	if (boot.petty_cash_only) return to.name === "PettyCash" ? true : { name: "PettyCash" }
	if (to.meta.pettyCash) return boot.can_post || boot.petty_boxes?.length ? true : { name: "Home" }
	if (to.meta.managerOnly && !boot.is_settings_manager) return { name: "Home" }
	if (to.meta.record) {
		const r = records[to.params.slug]
		if (!r || !canRead(r) || (to.meta.record === "create" && !canCreate(r))) return { name: "Home" }
	}
	return to.meta.postOnly && !boot.can_post ? { name: "Home" } : true
})

export default router
