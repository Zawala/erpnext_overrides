<template>
	<div class="app-bg flex h-[100dvh] text-gray-900">
		<!-- Desktop sidebar -->
		<aside class="hidden md:flex w-56 lg:w-60 shrink-0 flex-col border-r bg-white">
			<router-link to="/" class="flex h-14 flex-col justify-center gap-1 border-b px-4">
				<img :src="logo" class="h-6 w-auto max-w-[150px] self-start object-contain" alt="Logo" />
				<div class="truncate text-xs text-gray-500"><span class="font-medium text-gray-800">Sales</span> · {{ "Lead to purchase order" }}</div>
			</router-link>
			<nav class="flex-1 overflow-y-auto p-2 space-y-0.5">
				<NavItem to="/" icon="home" label="Home" exact />
				<div class="px-2 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-gray-400">Selling</div>
				<NavItem v-for="dt in selling" :key="dt.slug" :to="`/${dt.slug}`" :icon="dt.icon" :label="dt.label" />
				<NavItem v-if="boot.can_view_tenders" to="/tenders" icon="briefcase" label="Tenders" />
				<template v-if="fulfil.length">
					<div class="px-2 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-gray-400">Deliver & bill</div>
					<NavItem v-for="dt in fulfil" :key="dt.slug" :to="`/${dt.slug}`" :icon="dt.icon" :label="dt.label" />
				</template>
				<div class="px-2 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-gray-400">Buying</div>
				<NavItem v-for="dt in buying" :key="dt.slug" :to="`/${dt.slug}`" :icon="dt.icon" :label="dt.label" />
				<NavItem v-if="boot.can_import_suppliers" to="/suppliers" icon="users" label="Suppliers" />
				<template v-if="boot.is_approver">
					<div class="px-2 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-gray-400">Manager</div>
					<NavItem to="/approvals" icon="check-circle" label="Approvals" :badge="approvalCount" />
				</template>
				<div class="px-2 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-gray-400">Insight</div>
				<NavItem to="/reports" icon="bar-chart-2" label="Reports" />
				<NavItem v-if="boot.is_settings_manager" to="/settings" icon="settings" label="Settings" />
			</nav>
			<div class="border-t p-3 flex items-center gap-2">
				<div class="h-8 w-8 rounded-full bg-gray-200 grid place-items-center text-sm font-medium text-gray-700 overflow-hidden">
					<img v-if="boot.user_image" :src="boot.user_image" class="h-full w-full object-cover" alt="" />
					<span v-else>{{ initials }}</span>
				</div>
				<div class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium">{{ boot.full_name }}</div>
					<div class="flex gap-2 text-xs text-gray-500"><a href="/launcher" class="hover:text-gray-800">All apps</a><span>·</span><a href="/desk" class="hover:text-gray-800">Desk ↗</a></div>
				</div>
				<button class="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Log out" @click="logout">
					<FeatherIcon name="log-out" class="h-4 w-4" />
				</button>
			</div>
		</aside>

		<main class="flex-1 min-w-0 flex flex-col pb-[calc(56px+env(safe-area-inset-bottom))] md:pb-0">
			<slot />
		</main>

		<!-- Mobile bottom tabs -->
		<nav class="md:hidden fixed inset-x-0 bottom-0 z-30 border-t bg-white pb-safe-bottom">
			<div class="grid grid-cols-5 h-14">
				<TabItem to="/" icon="home" label="Home" exact />
				<TabItem to="/leads" icon="user-plus" label="Leads" />
				<TabItem to="/quotations" icon="file-text" label="Quotes" />
				<TabItem to="/sales-orders" icon="shopping-bag" label="Orders" />
				<button class="flex flex-col items-center justify-center gap-0.5 text-gray-500 relative" @click="moreOpen = true">
					<FeatherIcon name="menu" class="h-5 w-5" />
					<span class="text-[11px]">More</span>
					<span v-if="approvalCount" class="absolute top-1.5 right-[calc(50%-18px)] h-2 w-2 rounded-full bg-red-500" />
				</button>
			</div>
		</nav>

		<Dialog v-model="moreOpen" :options="{ title: 'More', size: 'sm', position: 'top' }">
			<template #body-content>
				<div class="-mx-2 space-y-0.5" @click="moreOpen = false">
					<NavItem v-if="boot.can_view_tenders" to="/tenders" icon="briefcase" label="Tenders" />
					<NavItem v-for="dt in more" :key="dt.slug" :to="`/${dt.slug}`" :icon="dt.icon" :label="dt.label" />
					<NavItem v-if="boot.can_import_suppliers" to="/suppliers" icon="users" label="Suppliers" />
					<NavItem v-if="boot.is_approver" to="/approvals" icon="check-circle" label="Approvals" :badge="approvalCount" />
					<NavItem to="/reports" icon="bar-chart-2" label="Reports" />
					<NavItem v-if="boot.is_settings_manager" to="/settings" icon="settings" label="Settings" />
					<a href="/launcher" class="flex items-center gap-3 rounded px-2 py-2 text-base text-gray-700 hover:bg-gray-100">
						<FeatherIcon name="grid" class="h-4 w-4" /> All apps
					</a>
					<a href="/desk" class="flex items-center gap-3 rounded px-2 py-2 text-base text-gray-700 hover:bg-gray-100">
						<FeatherIcon name="external-link" class="h-4 w-4" /> Open desk
					</a>
					<button class="w-full flex items-center gap-3 rounded px-2 py-2 text-base text-gray-700 hover:bg-gray-100" @click="logout">
						<FeatherIcon name="log-out" class="h-4 w-4" /> Log out
					</button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, ref, h, onMounted } from "vue"
import { RouterLink, useRoute } from "vue-router"
import { Dialog, FeatherIcon, call } from "frappe-ui"
import { boot } from "@/boot"
import { doctypes, can } from "@/doctypes"
import { approvalCount, loadApprovals } from "@/data/approvals"

// the logo the rest of the system uses (Website / Navbar Settings), from the page boot
const logo = boot.app_logo || "/assets/erp_overrides/manifest/favicon-196.png"
const allowed = (list) => list.filter((d) => can(d)).map((d) => doctypes[d])
const selling = allowed(["Lead", "Opportunity", "Quotation", "Sales Order"])
const fulfil = allowed(["Delivery Note", "Sales Invoice"])
const buying = allowed(["Purchase Order", "Purchase Receipt"])
const more = allowed(["Opportunity", "Delivery Note", "Sales Invoice", "Purchase Order", "Purchase Receipt"])
const moreOpen = ref(false)
onMounted(() => loadApprovals().catch(() => {}))
const route = useRoute()

const initials = computed(() =>
	(boot.full_name || "").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()
)

const isActive = (to, exact) => (exact ? route.path === to : route.path === to || route.path.startsWith(to + "/"))

const NavItem = (props) =>
	h(RouterLink, {
		to: props.to,
		class: [
			"flex items-center gap-3 rounded px-2 py-1.5 text-base transition-colors",
			isActive(props.to, props.exact) ? "nav-active font-medium" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
		],
	}, () => [
		h(FeatherIcon, { name: props.icon, class: "h-4 w-4 shrink-0" }),
		h("span", { class: "flex-1 truncate" }, props.label),
		props.badge ? h("span", { class: "rounded-full bg-red-500 px-1.5 text-xs font-medium text-white" }, props.badge) : null,
	])
NavItem.props = ["to", "icon", "label", "exact", "badge"]

const TabItem = (props) =>
	h(RouterLink, {
		to: props.to,
		class: ["flex flex-col items-center justify-center gap-0.5", isActive(props.to, props.exact) ? "tab-active" : "text-gray-500"],
	}, () => [h(FeatherIcon, { name: props.icon, class: "h-5 w-5" }), h("span", { class: "text-[11px]" }, props.label)])
TabItem.props = ["to", "icon", "label", "exact"]

async function logout() {
	await call("logout")
	window.location.href = "/login?redirect-to=/sales"
}
</script>
