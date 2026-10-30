<template>
	<div class="app-bg flex h-[100dvh] text-gray-900">
		<!-- Desktop sidebar -->
		<aside class="hidden md:flex w-56 lg:w-60 shrink-0 flex-col border-r bg-white">
			<router-link to="/" class="flex h-14 flex-col justify-center gap-1 border-b px-4">
				<img :src="logo" class="h-6 w-auto max-w-[150px] self-start object-contain" alt="Logo" />
				<div class="truncate text-xs text-gray-500"><span class="font-medium text-gray-800">HR</span> · {{ boot.is_hr ? "Leave, payroll and people" : boot.employee_only ? "Who's off and reviews" : "Your team" }}</div>
			</router-link>
			<nav class="flex-1 overflow-y-auto p-2 space-y-0.5">
				<template v-for="group in groups" :key="group.label">
					<div v-if="group.label" class="px-2 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-gray-400">
						{{ group.label }}
					</div>
					<NavItem v-for="item in group.items" :key="item.to" v-bind="item" />
				</template>
			</nav>
			<div class="border-t p-3 flex items-center gap-2">
				<div class="h-8 w-8 rounded-full bg-gray-200 grid place-items-center text-sm font-medium text-gray-700 overflow-hidden">
					<img v-if="boot.user_image" :src="boot.user_image" class="h-full w-full object-cover" alt="" />
					<span v-else>{{ initials }}</span>
				</div>
				<div class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium">{{ boot.full_name }}</div>
					<div class="flex gap-2 text-xs text-gray-500"><a href="/launcher" class="hover:text-gray-800">All apps</a><span>·</span>
						<a v-if="boot.employee_only" href="/hrms" class="hover:text-gray-800">My HR</a>
						<a v-else href="/desk" class="hover:text-gray-800">Desk ↗</a></div>
				</div>
				<button class="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Log out" aria-label="Log out" @click="logout">
					<FeatherIcon name="log-out" class="h-4 w-4" />
				</button>
			</div>
		</aside>

		<main class="flex-1 min-w-0 flex flex-col pb-[calc(56px+env(safe-area-inset-bottom))] md:pb-0">
			<slot />
		</main>

		<!-- Mobile bottom tabs -->
		<nav class="md:hidden fixed inset-x-0 bottom-0 z-30 border-t bg-white pb-safe-bottom">
			<div v-if="boot.employee_only" class="grid h-14" :class="hasReviewPages ? 'grid-cols-3' : 'grid-cols-2'">
				<TabItem to="/calendar" icon="calendar" label="Who's off" />
				<TabItem v-if="hasReviewPages" to="/my-reviews" icon="check-square" label="Reviews" />
				<a href="/hrms" class="flex flex-col items-center justify-center gap-0.5 text-gray-500">
					<FeatherIcon name="user-check" class="h-5 w-5" /><span class="text-[11px]">My HR</span>
				</a>
			</div>
			<div v-else class="grid h-14" :class="boot.is_hr ? 'grid-cols-5' : 'grid-cols-4'">
				<TabItem to="/" icon="home" label="Home" exact />
				<TabItem to="/inbox" icon="inbox" label="Inbox" :dot="inboxCount > 0" />
				<template v-if="boot.is_hr">
					<TabItem to="/people" icon="users" label="People" />
					<TabItem to="/payroll" icon="dollar-sign" label="Payroll" />
					<button class="flex flex-col items-center justify-center gap-0.5 text-gray-500" @click="moreOpen = true">
						<FeatherIcon name="menu" class="h-5 w-5" />
						<span class="text-[11px]">More</span>
					</button>
				</template>
				<template v-else>
					<TabItem to="/calendar" icon="calendar" label="Who's off" />
					<TabItem to="/balances" icon="pie-chart" label="Balances" />
				</template>
			</div>
		</nav>

		<Dialog v-model="moreOpen" :options="{ title: 'More', size: 'sm', position: 'top' }">
			<template #body-content>
				<div class="-mx-2 space-y-0.5" @click="moreOpen = false">
					<NavItem v-for="item in more" :key="item.to" v-bind="item" />
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
import { hr } from "../api"
import { inboxCount, setInboxCount } from "../data/inbox"

// the logo the rest of the system uses (Website / Navbar Settings), from the page boot
const logo = boot.app_logo || "/assets/erp_overrides/manifest/favicon-196.png"
const moreOpen = ref(false)
const hasReviewPages = !!(boot.has_reviews || boot.has_reports)
const route = useRoute()

const groups = computed(() => {
	const inbox = { to: "/inbox", icon: "inbox", label: "Inbox", badge: inboxCount.value }
	const calendar = { to: "/calendar", icon: "calendar", label: "Who's off" }
	const mine = hasReviewPages ? [{ to: "/my-reviews", icon: "check-square", label: boot.has_reports ? "Reviews" : "My reviews" }] : []
	if (boot.employee_only) return [{ items: [calendar, ...mine] }]
	if (!boot.is_hr) {
		return [{ items: [{ to: "/", icon: "home", label: "Home", exact: true }, inbox, calendar, ...mine,
			{ to: "/balances", icon: "pie-chart", label: "Team balances" }] }]
	}
	return [
		{ items: [{ to: "/", icon: "home", label: "Home", exact: true }, inbox, calendar] },
		{ label: "Leave & time", items: [
			{ to: "/leave", icon: "calendar", label: "Leave" },
			{ to: "/balances", icon: "pie-chart", label: "Balances" },
			{ to: "/attendance", icon: "check-square", label: "Attendance" },
		] },
		{ label: "Money", items: [
			{ to: "/payroll", icon: "dollar-sign", label: "Payroll" },
			{ to: "/salaries", icon: "edit-3", label: "Salaries" },
			{ to: "/pay-setup", icon: "sliders", label: "Pay setup" },
			{ to: "/pay-report", icon: "file-text", label: "Pay report" },
			{ to: "/expenses", icon: "credit-card", label: "Expenses" },
		] },
		{ label: "Reviews", items: [
			{ to: "/reviews", icon: "clipboard", label: "Bi-weekly reviews" },
			...(hasReviewPages ? [{ to: "/my-reviews", icon: "check-square", label: "My reviews" }] : []),
		] },
		{ label: "People", items: [
			{ to: "/people", icon: "users", label: "Employees" },
			{ to: "/reports", icon: "bar-chart-2", label: "Reports" },
			...(boot.is_settings_manager ? [{ to: "/settings", icon: "settings", label: "Settings" }] : []),
		] },
	]
})
const more = computed(() =>
	groups.value.flatMap((g) => g.items).filter((i) => !["/", "/inbox", "/people", "/payroll"].includes(i.to))
)

onMounted(() => boot.employee_only || hr("get_dashboard").then((d) => setInboxCount(d.pending)).catch(() => {}))

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
		class: ["relative flex flex-col items-center justify-center gap-0.5", isActive(props.to, props.exact) ? "tab-active" : "text-gray-500"],
	}, () => [
		h(FeatherIcon, { name: props.icon, class: "h-5 w-5" }),
		h("span", { class: "text-[11px]" }, props.label),
		props.dot ? h("span", { class: "absolute top-1.5 right-[calc(50%-18px)] h-2 w-2 rounded-full bg-red-500" }) : null,
	])
TabItem.props = ["to", "icon", "label", "exact", "dot"]

async function logout() {
	await call("logout")
	window.location.href = "/login?redirect-to=/hrms-admin"
}
</script>
