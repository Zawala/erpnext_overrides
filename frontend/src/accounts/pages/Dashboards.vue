<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Dashboards" :subtitle="`Cash, purchases, profit and budget — in ${boot.currency}, other currencies at today's rate`">
			<Button v-if="boot.can_post" variant="solid" icon-left="send" label="Make a payment" @click="paying = true" />
		</PageHeader>
		<PaymentDialog v-if="boot.can_post" v-model="paying" @paid="reload" />

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<!-- Cash flow -->
			<section class="rounded-lg border bg-white p-4">
				<header class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
					<div>
						<h3 class="font-semibold">Cash flow — money in and out of the banks</h3>
						<p class="text-sm text-gray-500">Last 12 months. Transfers between our own accounts are left out.</p>
					</div>
					<div v-if="flow" class="text-sm">
						Net <b :class="flowNet < 0 ? 'text-red-700' : 'text-green-700'" class="tabular">{{ cur(flowNet) }}</b>
					</div>
				</header>
				<div v-if="!flow" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<BarChart v-else :months="flow.months" :series="FLOW_SERIES" label="Money in and out by month" :format="cur" />
				<p v-if="flow && !flowAny" class="mt-2 text-sm text-amber-700">Nothing posted to the banks yet — this fills in as statement lines are reconciled.</p>
			</section>

			<!-- Purchases -->
			<section id="purchases" class="scroll-mt-24 rounded-lg border bg-white">
				<header class="flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-3">
					<div>
						<h3 class="font-semibold">Purchases</h3>
						<p class="text-sm text-gray-500">Supplier invoices and purchase orders, before tax.</p>
					</div>
					<span class="flex gap-3 text-sm">
						<a v-if="buy?.can_orders" :href="deskUrl('Purchase Order', 'new')" target="_blank" class="text-blue-700 hover:underline">New purchase order ↗</a>
						<a v-if="buy?.can_orders" :href="deskUrl('Purchase Order')" target="_blank" class="text-blue-700 hover:underline">All orders ↗</a>
						<router-link v-if="buy?.can_invoices" to="/records/purchase-invoices" class="text-blue-700 hover:underline">All invoices</router-link>
					</span>
				</header>
				<div v-if="!buy" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<div v-else-if="!buy.can_orders && !buy.can_invoices" class="px-4 py-6 text-sm text-gray-500">
					Your role can't see purchase orders or supplier invoices.
				</div>
				<template v-else>
					<div class="grid grid-cols-2 border-b lg:grid-cols-4">
						<div v-for="(f, i) in buyFigures" :key="f.label" class="px-4 py-3"
							:class="[i % 2 === 0 && 'border-r', i < 2 && buyFigures.length > 2 && 'border-b lg:border-b-0', i === 1 && buyFigures.length > 2 && 'lg:border-r']">
							<div class="text-xs text-gray-500">{{ f.label }}</div>
							<div class="text-lg font-semibold tabular" :class="f.warn ? 'text-amber-700' : ''">{{ f.value }}</div>
							<div class="text-xs text-gray-500 tabular" :class="f.warn ? 'text-amber-700' : ''">{{ f.hint }}</div>
						</div>
					</div>
					<div class="px-4 pt-3">
						<div class="text-xs font-medium uppercase tracking-wide text-gray-500">Last 12 months</div>
						<BarChart :months="buy.months" :series="buySeries" label="Purchases by month" :format="cur" />
						<p v-if="!buyAny" class="mt-2 text-sm text-gray-500">No submitted purchase orders or supplier invoices in the last 12 months.</p>
					</div>

					<div class="mt-3 grid grid-cols-1 border-t xl:grid-cols-[minmax(0,1fr)_380px] xl:divide-x">
						<!-- Open orders -->
						<div v-if="buy.can_orders" class="min-w-0">
							<div class="px-4 pt-3 pb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Open purchase orders</div>
							<p v-if="!buy.recent_orders.length" class="px-4 pb-4 text-sm text-gray-500">
								No open purchase orders. Orders appear here once submitted, until they are fully received and billed.
							</p>
							<div v-else class="overflow-x-auto">
								<table class="w-full text-sm tabular">
									<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
										<tr><th class="px-4 py-2">Supplier</th><th class="px-2 py-2">Ordered · due</th><th class="px-2 py-2 text-right">Value</th>
											<th class="px-2 py-2">Received</th><th class="px-4 py-2">Billed</th></tr>
									</thead>
									<tbody>
										<tr v-for="o in buy.recent_orders" :key="o.name" class="border-t hover:bg-gray-50" :class="late(o) ? 'bg-amber-50' : ''">
											<td class="max-w-[16rem] px-4 py-2">
												<a :href="deskUrl('Purchase Order', o.name)" target="_blank" class="block truncate font-medium hover:underline">{{ o.supplier_name || o.supplier }}</a>
												<div class="truncate text-xs text-gray-500">{{ o.name }} · {{ o.status }}</div>
											</td>
											<td class="whitespace-nowrap px-2 py-2">{{ date(o.transaction_date) }}
												<div class="text-xs" :class="late(o) ? 'text-amber-700' : 'text-gray-500'">{{ late(o) ? "late, was due" : "due" }} {{ date(o.schedule_date) }}</div></td>
											<td class="whitespace-nowrap px-2 py-2 text-right">{{ cur(o.grand_total, o.currency) }}
												<div v-if="o.currency !== buy.currency" class="text-xs text-gray-500">≈ {{ cur(o.base_grand_total) }}</div></td>
											<td class="px-2 py-2"><Pct :value="o.per_received" /></td>
											<td class="px-4 py-2"><Pct :value="o.per_billed" /></td>
										</tr>
									</tbody>
								</table>
								<p v-if="buy.orders.open > buy.recent_orders.length" class="border-t px-4 py-2 text-xs text-gray-500">
									Latest {{ buy.recent_orders.length }} of {{ buy.orders.open }} open orders.
									<a :href="deskUrl('Purchase Order') + '?docstatus=1'" target="_blank" class="text-blue-700 hover:underline">See them all ↗</a>
								</p>
							</div>
						</div>

						<!-- Suppliers -->
						<div v-if="buy.can_invoices" class="px-4 py-3" :class="buy.can_orders ? 'border-t xl:border-t-0' : 'xl:col-span-2'">
							<div class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Biggest suppliers this year</div>
							<p v-if="!buy.top_suppliers.length" class="text-sm text-gray-500">No supplier invoices this year yet.</p>
							<div v-for="s in buy.top_suppliers" :key="s.supplier" class="mb-1.5">
								<div class="flex justify-between gap-2 text-sm"><span class="truncate">{{ s.supplier_name || s.supplier }}</span><span class="tabular">{{ cur(s.amount) }}</span></div>
								<div class="h-1.5 rounded bg-gray-100"><div class="h-1.5 rounded bg-blue-500" :style="{ width: `${(s.amount / buy.top_suppliers[0].amount) * 100}%` }" /></div>
							</div>
						</div>
					</div>
				</template>
			</section>

			<div class="grid grid-cols-1 gap-4 xl:grid-cols-2 items-start">
				<!-- Cash by bank -->
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Cash in each account</h3>
					<div v-if="!dash" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<ul v-else class="divide-y">
						<li v-for="c in dash.cash" :key="c.account" class="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
							<span class="min-w-0 truncate">{{ c.name }}</span>
							<span class="text-right tabular">
								<span :class="c.balance < 0 ? 'text-red-700' : ''">{{ cur(c.balance, c.currency) }}</span>
								<span v-if="c.currency !== dash.currency" class="block text-xs text-gray-500">≈ {{ cur(c.today_value) }}</span>
							</span>
						</li>
						<li class="flex justify-between px-4 py-2.5 font-semibold"><span>Total</span><span class="tabular">{{ cur(dash.cash_total) }}</span></li>
					</ul>
					<p v-if="dash?.cash.some((c) => c.balance < 0)" class="border-t px-4 py-2 text-xs text-amber-700">
						A negative bank balance usually means the statement lines aren't all reconciled yet, or an opening balance is missing.
					</p>
				</section>

				<!-- Profit and loss -->
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Profit and loss</h3>
					<div v-if="!pnl" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<template v-else>
						<div class="grid grid-cols-3 divide-x">
							<div v-for="p in [['This month', pnl.this_month], ['Last month', pnl.last_month], ['Year to date', pnl.year_to_date]]" :key="p[0]" class="px-4 py-3">
								<div class="text-xs text-gray-500">{{ p[0] }}</div>
								<div class="text-lg font-semibold tabular" :class="p[1].profit < 0 ? 'text-red-700' : ''">{{ cur(p[1].profit) }}</div>
								<div class="text-xs text-gray-500 tabular">in {{ cur(p[1].income) }} · out {{ cur(p[1].expense) }}</div>
							</div>
						</div>
						<div v-if="pnl.top_expenses.length" class="border-t px-4 py-3">
							<div class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Biggest costs this year</div>
							<div v-for="e in pnl.top_expenses" :key="e.account" class="mb-1.5">
								<div class="flex justify-between text-sm"><span class="truncate">{{ e.account }}</span><span class="tabular">{{ cur(e.amount) }}</span></div>
								<div class="h-1.5 rounded bg-gray-100"><div class="h-1.5 rounded bg-gray-500" :style="{ width: `${(e.amount / pnl.top_expenses[0].amount) * 100}%` }" /></div>
							</div>
						</div>
					</template>
				</section>

				<!-- Budget -->
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Budget against actual <span v-if="budget" class="font-normal text-gray-500">· {{ budget.fiscal_year }}</span></h3>
					<div v-if="!budget" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<div v-else-if="!budget.rows.length" class="px-4 py-6 text-sm text-gray-500">
						No budget for {{ budget.fiscal_year }} yet. Set one per account and cost centre in desk and this shows budget, actual and what's left.
						<a href="/desk/budget/new" target="_blank" class="mt-2 block text-blue-700 hover:underline">Set up a budget ↗</a>
					</div>
					<table v-else class="w-full text-sm tabular">
						<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
							<tr><th class="px-4 py-2">Account</th><th class="px-2 py-2 text-right">Budget</th><th class="px-2 py-2 text-right">Actual</th><th class="px-4 py-2 text-right">Left</th></tr>
						</thead>
						<tbody>
							<tr v-for="r in budget.rows" :key="r.account + r.against" class="border-t">
								<td class="px-4 py-2">{{ r.account }}<div class="text-xs text-gray-500">{{ r.against }}</div></td>
								<td class="px-2 py-2 text-right">{{ cur(r.budget) }}</td>
								<td class="px-2 py-2 text-right">{{ cur(r.actual) }}</td>
								<td class="px-4 py-2 text-right" :class="r.variance < 0 ? 'text-red-700' : 'text-green-700'">{{ cur(r.variance) }}</td>
							</tr>
						</tbody>
					</table>
				</section>

				<!-- Reports -->
				<section class="rounded-lg border bg-white">
					<header class="flex items-baseline justify-between gap-3 border-b px-4 py-3">
						<h3 class="font-semibold">Financial statements</h3>
						<router-link to="/reports" class="text-sm text-blue-700 hover:underline">All reports →</router-link>
					</header>
					<div class="grid grid-cols-1 gap-px bg-gray-100 sm:grid-cols-2">
						<a v-for="r in reports" :key="r.name" :href="r.url" target="_blank" class="bg-white px-4 py-3 hover:bg-gray-50">
							<div class="text-sm font-medium">{{ r.name }} ↗</div>
							<div class="text-xs text-gray-500">{{ r.description }}</div>
						</a>
					</div>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, h, nextTick, ref } from "vue"
import { useRoute } from "vue-router"
import { LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import { date, today } from "@/utils/format"
import { acc, cur, deskUrl, fail } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"
import BarChart from "@/components/BarChart.vue"
import PaymentDialog from "../components/PaymentDialog.vue"

const route = useRoute()
const flow = ref(null)
const dash = ref(null)
const pnl = ref(null)
const budget = ref(null)
const buy = ref(null)
const reports = ref([])
const paying = ref(false)
const todayStr = today()

const FLOW_SERIES = [
	{ key: "money_in", label: "In", class: "fill-green-500", swatch: "bg-green-500" },
	{ key: "money_out", label: "Out", class: "fill-gray-400", swatch: "bg-gray-400" },
]
const flowNet = computed(() => (flow.value?.months || []).reduce((s, m) => s + m.net, 0))
const flowAny = computed(() => (flow.value?.months || []).some((m) => m.money_in || m.money_out))

const buySeries = computed(() => [
	buy.value?.can_invoices && { key: "invoiced", label: "Invoiced by suppliers", class: "fill-blue-500", swatch: "bg-blue-500" },
	buy.value?.can_orders && { key: "ordered", label: "Ordered", class: "fill-gray-400", swatch: "bg-gray-400" },
].filter(Boolean))
const buyAny = computed(() => (buy.value?.months || []).some((m) => m.invoiced || m.ordered))
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`
const buyFigures = computed(() => {
	const b = buy.value, o = b.orders
	return [
		b.can_invoices && { label: "Invoiced this month", value: cur(b.this_month.total), hint: plural(b.this_month.invoices, "invoice") },
		b.can_invoices && { label: "Invoiced this year", value: cur(b.year_to_date.total), hint: plural(b.year_to_date.invoices, "invoice") },
		o && { label: "On order, not yet billed", value: cur(o.to_bill), hint: `${plural(o.to_bill_n, "order")}${o.drafts ? ` · ${o.drafts} draft${o.drafts === 1 ? "" : "s"}` : ""}` },
		o && { label: "Still to be delivered", value: cur(o.to_receive), hint: o.late ? `${plural(o.late, "order")} late` : `${plural(o.to_receive_n, "order")} · none late`, warn: o.late > 0 },
	].filter(Boolean)
})
const late = (o) => o.per_received < 100 && o.schedule_date && o.schedule_date < todayStr

const Pct = (p) => h("div", { class: "flex items-center gap-1.5", title: `${Math.round(p.value || 0)}%` }, [
	h("div", { class: "h-1.5 w-12 rounded bg-gray-100" }, [h("div", { class: "h-1.5 rounded bg-green-500", style: { width: `${Math.min(100, p.value || 0)}%` } })]),
	h("span", { class: "text-xs text-gray-500" }, `${Math.round(p.value || 0)}%`),
])
Pct.props = ["value"]

function reload() {
	return Promise.all([
		acc("get_cash_flow", { months: 12 }).then((v) => (flow.value = v)),
		acc("get_dashboard").then((v) => (dash.value = v)),
		acc("get_purchases", { months: 12 }).then((v) => (buy.value = v)),
		acc("get_pnl").then((v) => (pnl.value = v)),
		acc("get_budget").then((v) => (budget.value = v)),
		// the statements here; every other report is on the Reports page
		acc("get_reports").then((v) => (reports.value = v[0]?.reports || [])),
	]).catch((e) => fail(e, "Could not load the dashboards"))
}
// Home's Purchase orders tile links to #purchases; the page scrolls inside its own box, so jump there by hand
reload().then(() => route.hash && nextTick(() => document.querySelector(route.hash)?.scrollIntoView()))
</script>
