<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Home" :subtitle="`${boot.company} · today in ${boot.currency}`">
			<Button v-if="boot.can_post" variant="solid" icon-left="send" label="Make a payment" @click="payBill(null)" />
		</PageHeader>

		<div v-if="!dash" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<router-link v-if="dash.petty_awaiting" to="/petty-cash"
				class="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 hover:border-amber-400">
				<FeatherIcon name="clock" class="h-5 w-5 shrink-0" />
				<span class="flex-1"><b>{{ dash.petty_awaiting }} petty cash voucher{{ dash.petty_awaiting === 1 ? "" : "s" }}</b> awaiting your approval</span>
				<FeatherIcon name="arrow-right" class="h-4 w-4" />
			</router-link>

			<!-- Tiles -->
			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4 2xl:grid-cols-7">
				<Tile label="Cash in all accounts" :value="cur(dash.cash_total)" :hint="`${dash.cash.length} accounts`" to="/dashboards" />
				<Tile label="Owed to us" :value="cur(dash.receivable.total)" :hint="dash.receivable.overdue ? `${cur(dash.receivable.overdue)} overdue` : 'nothing overdue'"
					:warn="dash.receivable.overdue > 0" :to="boot.can_post ? '/receivables' : null" />
				<Tile label="We owe" :value="cur(dash.payable.total)" :hint="dash.payable.overdue ? `${cur(dash.payable.overdue)} overdue` : 'nothing overdue'"
					:warn="dash.payable.overdue > 0" :to="boot.can_post ? '/payables' : null" />
				<Tile v-if="dash.purchases" label="Purchase orders" :value="cur(dash.purchases.to_bill)"
					:hint="`${dash.purchases.open} open · ${dash.purchases.late ? `${dash.purchases.late} late` : 'none late'}`"
					:warn="dash.purchases.late > 0" to="/dashboards#purchases" />
				<Tile label="Bank lines to reconcile" :value="dash.to_reconcile" :warn="dash.to_reconcile > 0" :to="boot.can_post ? '/bank' : null" />
				<Tile label="This month" :value="cur(dash.money_in - dash.money_out)" :hint="`in ${cur(dash.money_in)} · out ${cur(dash.money_out)}`" to="/dashboards" />
				<Tile label="RBZ rate" :value="dash.rate.value ? Number(dash.rate.value).toFixed(4) : '—'" :hint="dash.rate.date ? `ZWG per USD · ${date(dash.rate.date)}` : 'not loaded'"
					:to="boot.can_post ? '/rates' : null" />
			</div>

			<div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_420px] items-start">
				<!-- Setup health -->
				<section v-if="boot.can_post" class="rounded-lg border bg-white">
					<header class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
						<div>
							<h3 class="font-semibold">Health check</h3>
							<p class="text-sm text-gray-500">The setup gaps behind most "the numbers look wrong" questions. Fix them once.</p>
						</div>
						<Chips v-if="health" v-model="group" :options="groupChips" />
					</header>
					<div v-if="!health" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<Empty v-else-if="!shownIssues.length" icon="check-circle">Nothing to fix.</Empty>
					<ul v-else class="divide-y">
						<li v-for="i in shownIssues" :key="i.check + i.message" class="flex items-start gap-3 px-4 py-3">
							<FeatherIcon :name="i.severity === 'error' ? 'x-circle' : 'alert-triangle'" class="mt-0.5 h-5 w-5 shrink-0"
								:class="i.severity === 'error' ? 'text-red-500' : 'text-amber-500'" />
							<div class="min-w-0 flex-1 text-sm">{{ i.message }}</div>
							<Button size="sm" icon-right="arrow-right" label="Fix" @click="fix(i)" />
						</li>
					</ul>
				</section>

				<div class="space-y-4" :class="boot.can_post ? '' : 'xl:col-span-2'">
				<!-- Bills to pay -->
				<section v-if="boot.can_post" class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h3 class="font-semibold">Bills to pay next</h3>
						<span class="flex gap-3 text-sm">
							<router-link to="/payments" class="text-blue-700 hover:underline">Payments made</router-link>
							<router-link to="/payables" class="text-blue-700 hover:underline">All we owe</router-link>
						</span>
					</header>
					<Empty v-if="!dash.bills_due.length" icon="check-circle">No supplier bills waiting.</Empty>
					<div v-for="b in dash.bills_due" :key="b.name" class="flex items-center gap-3 border-t px-4 py-2.5 text-sm first-of-type:border-t-0">
						<div class="min-w-0 flex-1">
							<div class="truncate font-medium">{{ b.supplier_name || b.supplier }}</div>
							<div class="truncate text-xs" :class="b.due_date < todayStr ? 'text-amber-700' : 'text-gray-500'">
								{{ b.bill_no || b.name }} · {{ b.due_date < todayStr ? "was due" : "due" }} {{ date(b.due_date) }}</div>
						</div>
						<span v-if="b.match" class="rounded px-1.5 py-0.5 text-xs" :class="MATCH_THEME[b.match.status]" :title="b.match.message">{{ b.match.label }}</span>
						<span class="tabular">{{ cur(b.outstanding_amount, b.currency) }}</span>
						<Button size="sm" label="Pay" :disabled="b.match && !b.match.payable"
							:title="b.match && !b.match.payable ? `Can't pay yet: ${b.match.message}` : ''" @click="payBill(b)" />
					</div>
				</section>

				<!-- Asked about -->
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">{{ boot.can_post ? "Bank lines you've been asked about" : "Cash in each account" }}</h3>
					<template v-if="boot.can_post">
						<Empty v-if="!dash.assigned.length" icon="message-circle">Nobody has asked you about a line.</Empty>
						<router-link v-for="a in dash.assigned" :key="a.reference_name" :to="{ path: '/bank', query: { line: a.reference_name } }"
							class="block border-t px-4 py-2.5 text-sm first:border-t-0 hover:bg-gray-50">
							<div class="line-clamp-2">{{ strip(a.description) }}</div>
							<div class="text-xs text-gray-500">{{ a.assigned_by_full_name }} · {{ relative(a.creation) }}</div>
						</router-link>
					</template>
					<ul v-else class="divide-y">
						<li v-for="c in dash.cash" :key="c.account" class="flex justify-between px-4 py-2.5 text-sm">
							<span class="truncate">{{ c.name }}</span><span class="tabular">{{ cur(c.balance, c.currency) }}</span>
						</li>
					</ul>
				</section>
				</div>
			</div>
		</div>

		<PaymentDialog v-if="boot.can_post" v-model="paying" :bill="payingBill" @paid="load" />
	</div>
</template>

<script setup>
import { computed, h, ref } from "vue"
import { RouterLink, useRouter } from "vue-router"
import { LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import { date, relative, today } from "@/utils/format"
import { acc, cur, fail } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import Empty from "@/hr/components/Empty.vue"
import PaymentDialog from "../components/PaymentDialog.vue"
import { MATCH_THEME } from "../records"

const router = useRouter()
const dash = ref(null)
const health = ref(null)
const group = ref("all")
const GROUPS = { bank: "Bank", setup: "Setup", rates: "Rates", money: "Money owed", petty: "Petty cash" }
const groupChips = computed(() => [{ value: "all", label: "All", count: health.value.issues.length },
	...Object.entries(health.value.counts).map(([k, c]) => ({ value: k, label: GROUPS[k] || k, count: c }))])
const shownIssues = computed(() => (health.value?.issues || []).filter((i) => group.value === "all" || i.group === group.value))
const paying = ref(false)
const payingBill = ref(null)
const todayStr = today()
const strip = (s) => String(s || "").replace(/<[^>]+>/g, "")

function fix(i) {
	if (i.fix.route) router.push(i.fix.route)
	else window.open(i.fix.desk_url, "_blank")
}

function payBill(b) {
	payingBill.value = b
	paying.value = true
}

function load() {
	acc("get_dashboard").then((d) => (dash.value = d)).catch((e) => fail(e, "Could not load Home"))
}
load()
if (boot.can_post) acc("get_health").then((v) => (health.value = v)).catch(() => {})

const Tile = (p) => h(p.to ? RouterLink : "div", {
	...(p.to ? { to: p.to } : {}),
	class: ["block rounded-lg border bg-white px-4 py-3", p.to ? "hover:border-gray-400" : "", p.warn ? "border-amber-200" : ""],
}, () => [
	h("div", { class: "text-xs text-gray-500" }, p.label),
	h("div", { class: "mt-0.5 truncate text-xl font-semibold tabular" }, String(p.value)),
	p.hint ? h("div", { class: ["truncate text-xs", p.warn ? "text-amber-700" : "text-gray-500"] }, p.hint) : null,
])
Tile.props = ["label", "value", "hint", "to", "warn"]
</script>
