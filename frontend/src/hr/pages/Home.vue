<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="`${greeting}, ${firstName}`">
			<Button v-if="pendingTotal" variant="solid" icon-left="inbox" :label="`Inbox (${pendingTotal})`" @click="$router.push('/inbox')" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-6">
			<!-- Tiles: who's off, holidays, plus the queues -->
			<section class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
				<Tile label="On leave today" :value="dash?.on_leave_today" to="/calendar" />
				<Tile label="On leave this month" :value="dash?.on_leave_month" to="/calendar" />
				<Tile label="Holidays this month" :value="dash?.holidays?.length"
					:hint="holidayHint" />
				<Tile label="Waiting for approval" :value="pendingTotal" to="/inbox" :alert="pendingTotal > 0"
					:hint="dash ? `${dash.pending.leave} leave · ${dash.pending.expense} claims · ${dash.pending.attendance} attendance` : ''" />
				<Tile v-if="boot.is_hr" label="Claims to pay" :value="dash?.unpaid?.count" to="/expenses?tab=unpaid"
					:hint="dash?.unpaid?.amount ? money(dash.unpaid.amount) : 'Approved, not yet paid'" />
				<Tile v-if="boot.is_hr" label="Payroll this month" :value="payrollShort" to="/payroll"
					:hint="dash?.payroll?.label" small />
			</section>

			<!-- Who's off: today and the rest of the week, company-wide -->
			<router-link v-if="today && (today.off.length || today.later.length)" to="/calendar"
				class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-white px-4 py-3 text-sm hover:border-gray-400">
				<span class="font-semibold">Who's off</span>
				<span v-if="today.off.length" class="text-gray-700">
					Today: {{ today.off.map((l) => l.employee_name + (l.half_day ? " (½)" : "") + (l.pending ? " (waiting)" : "")).join(", ") }}
				</span>
				<span v-else class="text-gray-500">Everyone is in today.</span>
				<span v-if="today.later.length" class="text-gray-500">
					This week: {{ [...new Set(today.later.map((l) => l.employee_name))].join(", ") }}
				</span>
				<span class="ml-auto text-blue-700">Calendar →</span>
			</router-link>

			<!-- Bi-weekly reviews: progress for HR, what waits on a manager -->
			<router-link v-if="reviewLine" :to="boot.is_hr ? '/reviews' : '/my-reviews'"
				class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-white px-4 py-3 text-sm hover:border-gray-400">
				<span class="font-semibold">Bi-weekly reviews</span>
				<span class="text-gray-700">{{ reviewLine }}</span>
				<span class="ml-auto text-blue-700">Reviews →</span>
			</router-link>

			<!-- Health check -->
			<section v-if="boot.is_hr" class="rounded-lg border bg-white">
				<header class="flex flex-wrap items-center gap-3 border-b px-4 py-3">
					<div class="flex-1 min-w-0">
						<h2 class="font-semibold">Health check</h2>
						<p class="text-sm text-gray-500">
							The system is almost never wrong about arithmetic. It is missing a link — fix the link and the problem goes away.
						</p>
					</div>
					<Chips v-model="group" :options="groupOptions" />
				</header>

				<div v-if="!health" class="p-6 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<Empty v-else-if="!health.issues.length" icon="check-circle">
					Every active employee has a login, approvers, a holiday list, a leave balance and a salary assignment.
				</Empty>
				<div v-else class="divide-y">
					<!-- Company-wide setup first, then one group per check across employees -->
					<div v-for="c in checks" :key="c.check" class="px-4 py-3">
						<div class="flex items-start gap-3">
							<FeatherIcon :name="c.severity === 'warning' ? 'alert-triangle' : 'x-circle'" class="mt-0.5 h-5 w-5 shrink-0"
								:class="c.severity === 'warning' ? 'text-amber-500' : 'text-red-500'" />
							<div class="min-w-0 flex-1">
								<div class="font-medium">{{ c.title }}</div>
								<div class="text-sm text-gray-600">{{ c.message }}</div>
								<div v-if="c.people.length" class="mt-2 flex flex-wrap gap-1.5">
									<router-link v-for="p in visiblePeople(c)" :key="p.employee" :to="fixRoute(p)"
										class="rounded-full border bg-gray-50 px-2.5 py-0.5 text-sm text-gray-700 hover:border-gray-400 hover:bg-white">
										{{ p.employee_name }}
									</router-link>
									<button v-if="c.people.length > LIMIT && !expanded[c.check]" class="px-2 text-sm text-gray-500 underline"
										@click="expanded[c.check] = true">+{{ c.people.length - LIMIT }} more</button>
								</div>
							</div>
							<span v-if="c.people.length" class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-sm font-medium tabular">
								{{ c.people.length }}
							</span>
							<Button v-else size="sm" label="Fix" icon-right="arrow-right" @click="openFix(c.fix)" />
						</div>
					</div>
				</div>
			</section>

			<!-- Approver home: the team at a glance -->
			<section v-else class="rounded-lg border bg-white p-4">
				<h2 class="font-semibold">Your team</h2>
				<p class="mt-1 text-sm text-gray-600">
					{{ boot.team?.length || 0 }} people send their leave, claims or attendance requests to you.
					Approve or reject them in the <router-link to="/inbox" class="underline">Inbox</router-link>;
					their remaining days are under <router-link to="/balances" class="underline">Team balances</router-link>.
				</p>
			</section>

			<p class="text-center text-xs text-gray-400 pb-4">
				Leave has to be right before payroll can be — payment days come from approved leave.
			</p>
		</div>
	</div>
</template>

<script setup>
import { computed, h, reactive, ref } from "vue"
import { RouterLink, useRouter } from "vue-router"
import { LoadingIndicator, call } from "frappe-ui"
import { boot } from "@/boot"
import { money, date } from "@/utils/format"
import { hr } from "../api"
import { setInboxCount } from "../data/inbox"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import Empty from "../components/Empty.vue"

const router = useRouter()
const dash = ref(null)
const today = ref(null)
const reviewData = ref(null)
const reviewMine = ref(null)
if (boot.is_hr) call("erp_overrides.api.reviews.get_reviews").then((r) => (reviewData.value = r)).catch(() => {})
if (boot.has_reports || boot.has_reviews) call("erp_overrides.api.reviews.my_reviews").then((r) => (reviewMine.value = r)).catch(() => {})
const reviewLine = computed(() => {
	const parts = []
	const t = reviewData.value?.totals
	if (t && t.open + t.self_done + t.completed) {
		parts.push(`Last six weeks: ${t.completed} completed, ${t.open + t.self_done} in progress` + (t.overdue ? `, ${t.overdue} overdue` : ""))
	}
	const mine = reviewMine.value
	if (mine) {
		const now = new Date().toISOString().slice(0, 10)
		const waiting = mine.team.filter((r) => r.status === "Self done" || (r.status === "Open" && r.due_on < now)).length
			+ mine.mine.filter((r) => r.status === "Open").length
		if (waiting) parts.push(`${waiting} waiting on you`)
	}
	return parts.join(" · ")
})
call("erp_overrides.api.leave_calendar.get_today").then((t) => (today.value = t)).catch(() => {})
const health = ref(null)
const group = ref("all")
const expanded = reactive({})
const LIMIT = 12

const firstName = computed(() => (boot.full_name || "").split(" ")[0])
const greeting = computed(() => {
	const hour = new Date().getHours()
	return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
})
const pendingTotal = computed(() => (dash.value ? Object.values(dash.value.pending).reduce((a, b) => a + b, 0) : 0))
const holidayHint = computed(() => {
	const d = dash.value
	if (!d) return ""
	if (d.holidays.length) return d.holidays.map((x) => x.description).join(", ")
	return d.next_holiday ? `Next: ${d.next_holiday.description}, ${date(d.next_holiday.holiday_date)}` : "None on the list"
})
const payrollShort = computed(() => {
	const s = dash.value?.payroll?.state
	return { none: "—", draft: "Draft", employees: "Started", slips: "Review", submitted: "Pay", bank_draft: "Paying", paid: "Paid", queued: "…", failed: "Failed" }[s] ?? "—"
})

const TITLES = {
	leave_period: "No leave period", leave_policy: "No leave policy", include_holiday: "Holidays charged as leave",
	tax_slab: "No PAYE tax slab", empty_structure: "Empty salary structure", payable_account: "No payroll payable account",
	payslip_encryption: "Payslips not encrypted", claim_accounts: "Claim types without an account",
	claim_payable: "No expense claim payable account", user_id: "No User ID", leave_approver: "No leave approver",
	expense_approver: "No expense approver", reports_to: "No Reports To", holiday_list: "No holiday list",
	allocation: "No leave balance", assignment: "No salary assignment",
}
// what the person will say, and the fix
const EXPLAIN = {
	user_id: "“It won't let me log in.” Set User ID on their employee record.",
	leave_approver: "“I can't submit my leave.” Set a leave approver, or one for their department.",
	expense_approver: "Their claims wait for nobody. Set an expense approver.",
	reports_to: "No supervisor in the approval chain or the org chart.",
	holiday_list: "Public holidays get counted as leave days.",
	allocation: "“It says I have 0 days.” Assign the leave policy for this period.",
	assignment: "“No payslip this month.” Assign a salary structure with a real base, and submit it.",
}
const GROUPS = { access: "Approvals & access", leave: "Leave", payroll: "Payroll & claims" }
const groupOptions = computed(() => [
	{ value: "all", label: "All", count: health.value?.issues.length },
	...Object.entries(GROUPS).map(([value, label]) => ({ value, label, count: health.value?.counts[value] || 0 })),
])

const checks = computed(() => {
	const by = new Map()
	for (const i of health.value?.issues || []) {
		if (group.value !== "all" && i.group !== group.value) continue
		if (!by.has(i.check)) {
			by.set(i.check, { check: i.check, title: TITLES[i.check] || i.check, severity: i.severity, fix: i.fix,
				message: i.employee ? EXPLAIN[i.check] || i.message : i.message, people: [] })
		}
		if (i.employee) by.get(i.check).people.push(i)
	}
	// company-wide blockers first, then the most widespread gaps
	return [...by.values()].sort((a, b) => (a.people.length && !b.people.length ? 1 : !a.people.length && b.people.length ? -1 : b.people.length - a.people.length))
})
const visiblePeople = (c) => (expanded[c.check] ? c.people : c.people.slice(0, LIMIT))
const FIELD_FOR = { allocation: "balances", assignment: "assignment" }
const fixRoute = (p) => ({ path: p.fix.route, query: { fix: FIELD_FOR[p.check] || p.check } })

function openFix(fix) {
	if (fix.route) {
		const [path, qs] = fix.route.split("?")
		router.push({ path, query: Object.fromEntries(new URLSearchParams(qs || "")) })
	} else window.open(fix.desk_url, "_blank")
}

const Tile = (props) => {
	const inner = [
		h("div", { class: "text-sm text-gray-600" }, props.label),
		h("div", { class: ["mt-1 font-semibold tabular", props.small ? "text-xl" : "text-2xl", props.alert ? "text-red-600" : ""] }, props.value ?? "–"),
		props.hint ? h("div", { class: "mt-1 text-xs text-gray-500 line-clamp-2" }, props.hint) : null,
	]
	const cls = "rounded-lg border bg-white p-4 transition-colors"
	return props.to ? h(RouterLink, { to: props.to, class: cls + " hover:border-gray-400" }, () => inner) : h("div", { class: cls }, inner)
}
Tile.props = ["label", "value", "hint", "to", "alert", "small"]

hr("get_dashboard").then((d) => {
	dash.value = d
	setInboxCount(d.pending)
})
if (boot.is_hr) hr("get_health").then((r) => (health.value = r))
</script>
