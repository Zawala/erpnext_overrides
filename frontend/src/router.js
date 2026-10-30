import { createRouter, createWebHistory } from "vue-router"
import { bySlug } from "@/doctypes"
import { boot } from "@/boot"

const routes = [
	{ path: "/", name: "Home", component: () => import("@/pages/Home.vue") },
	{ path: "/approvals", name: "Approvals", component: () => import("@/pages/Approvals.vue") },
	{ path: "/reports", name: "Reports", component: () => import("@/pages/Reports.vue") },
	// before /:slug, which would take "reports" / "settings" / "tenders" / "suppliers" for a doctype
	{ path: "/tenders", name: "Tenders", component: () => import("@/pages/Tenders.vue"),
		beforeEnter: () => (boot.can_view_tenders ? true : { name: "Home" }) },
	{ path: "/settings", name: "Settings", component: () => import("@/pages/Settings.vue"),
		beforeEnter: () => (boot.is_settings_manager ? true : { name: "Home" }) },
	{ path: "/suppliers", name: "Suppliers", component: () => import("@/pages/Suppliers.vue"),
		beforeEnter: () => (boot.can_import_suppliers ? true : { name: "Home" }) },
	{
		path: "/:slug",
		name: "List",
		component: () => import("@/pages/ListPage.vue"),
		props: true,
		beforeEnter: (to) => (bySlug[to.params.slug] ? true : { name: "Home" }),
		children: [
			{ path: "new", name: "New", component: () => import("@/pages/DocPage.vue"), props: true },
			{ path: ":name", name: "Doc", component: () => import("@/pages/DocPage.vue"), props: true },
		],
	},
	{ path: "/:pathMatch(.*)*", redirect: "/" },
]

export default createRouter({
	history: createWebHistory("/sales"),
	routes,
})
