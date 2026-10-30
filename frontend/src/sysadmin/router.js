import { createRouter, createWebHistory } from "vue-router"

// System Managers only: the page itself (www/sys_admin.py) refuses everyone else
const routes = [
	{ path: "/", name: "Home", component: () => import("./pages/Home.vue") },
	{ path: "/users", name: "Users", component: () => import("./pages/Users.vue") },
	{ path: "/users/:user", name: "User", component: () => import("./pages/UserPage.vue"), props: true },
	{ path: "/inspector", name: "Inspector", component: () => import("./pages/Inspector.vue") },
	{ path: "/prices", name: "Prices", component: () => import("./pages/Prices.vue") },
	{ path: "/prices/import", name: "ImportPrices", component: () => import("./pages/ImportPrices.vue") },
	{ path: "/data", name: "Data", component: () => import("./pages/DataHub.vue") },
	// one route, so a finished upload moving to /data/import/<name> keeps the wizard where it is
	{ path: "/data/import/:name?", name: "DataImport", component: () => import("./pages/DataImport.vue"), props: true },
	{ path: "/data/export", name: "DataExport", component: () => import("./pages/DataExport.vue") },
	{ path: "/settings", name: "Settings", component: () => import("./pages/Settings.vue") },
	{ path: "/:pathMatch(.*)*", redirect: "/" },
]

export default createRouter({ history: createWebHistory("/sys-admin"), routes })
