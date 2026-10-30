<template>
	<section class="rounded-lg border bg-white">
		<header class="flex flex-wrap items-center gap-3 border-b px-4 py-3">
			<div class="flex-1 min-w-0">
				<h2 class="font-semibold">{{ scope === "team" ? "Team sales" : "My sales" }}</h2>
				<p class="text-sm text-gray-500">
					{{ scope === "team" ? "Everyone's quotations, orders and invoices" : "Quotations, orders and invoices you created" }},
					last 12 months, before tax{{ r ? ` (${r.currency})` : "" }}.
				</p>
			</div>
			<div v-if="boot.is_sales_manager" class="inline-flex rounded-md border p-0.5 text-sm" role="group" aria-label="Whose figures">
				<button v-for="o in SCOPES" :key="o.value" type="button" class="rounded px-3 py-1"
					:class="scope === o.value ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-100'"
					:aria-pressed="scope === o.value" @click="setScope(o.value)">{{ o.label }}</button>
			</div>
		</header>

		<div v-if="error" class="px-4 py-6 text-center text-sm text-red-600">{{ error }}</div>
		<div v-else-if="!r" class="px-4 py-10 text-center text-sm text-gray-400">Loading…</div>
		<div v-else class="space-y-6 p-4" :class="{ 'opacity-60': loading }">
			<!-- headline figures -->
			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<div v-for="f in figures" :key="f.label" class="rounded-lg bg-gray-50 p-3">
					<div class="text-sm text-gray-600">{{ f.label }}</div>
					<div class="mt-1 text-xl font-semibold tabular">{{ f.value }}</div>
					<div class="mt-0.5 text-xs text-gray-500">{{ f.hint }}</div>
				</div>
			</div>

			<p v-if="empty" class="py-4 text-center text-sm text-gray-500">
				{{ scope === "team" ? "No quotations this year yet." : "No quotations from you yet this year." }}
				<router-link to="/quotations/new" class="underline">Start one</router-link>
			</p>

			<template v-else>
				<BarChart :months="r.months" :series="series" :format="(v) => money(v, r.currency)" :label="`${title} by month`" />

				<!-- quote outcomes -->
				<div v-if="q">
					<h3 class="mb-2 text-sm font-medium text-gray-700">What happened to the quotations</h3>
					<div class="flex h-3 w-full overflow-hidden rounded-full bg-gray-100">
						<div v-for="o in outcomes" :key="o.key" :class="o.bar" :style="{ width: share(o.count) + '%' }" :title="`${o.label}: ${o.count}`" />
					</div>
					<ul class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
						<li v-for="o in outcomes" :key="o.key" class="flex items-center gap-1.5">
							<span class="inline-block h-2.5 w-2.5 rounded-full" :class="o.bar" />
							<span class="text-gray-700">{{ o.label }}</span>
							<span class="tabular text-gray-900">{{ o.count }}</span>
							<span class="tabular text-gray-500">· {{ compactMoney(o.total, r.currency) }}</span>
						</li>
					</ul>
					<p v-if="r.lost_reasons?.length" class="mt-2 text-xs text-gray-500">
						Lost because: {{ r.lost_reasons.map((l) => `${l.reason} (${l.n})`).join(", ") }}
					</p>
				</div>

				<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
					<div>
						<h3 class="mb-2 text-sm font-medium text-gray-700">Biggest customers this year</h3>
						<ul class="space-y-2">
							<li v-for="c in r.top_customers" :key="c.quotation_to + c.party">
								<div class="flex justify-between gap-3 text-sm">
									<span class="truncate">{{ c.name || c.party }}<span v-if="c.quotation_to !== 'Customer'" class="text-gray-400"> · {{ c.quotation_to }}</span></span>
									<span class="shrink-0 tabular">{{ compactMoney(c.quoted, r.currency) }}<span v-if="c.won" class="text-blue-700"> · won {{ compactMoney(c.won, r.currency) }}</span></span>
								</div>
								<div class="mt-1 h-1.5 rounded-full bg-gray-100">
									<div class="h-1.5 rounded-full bg-gray-400" :style="{ width: pct(c.quoted, maxCustomer) + '%' }">
										<div class="h-1.5 rounded-full bg-blue-500" :style="{ width: pct(c.won, c.quoted) + '%' }" />
									</div>
								</div>
							</li>
							<li v-if="!r.top_customers?.length" class="text-sm text-gray-500">None yet.</li>
						</ul>
					</div>
					<div>
						<h3 class="mb-2 text-sm font-medium text-gray-700">Most-quoted items this year</h3>
						<ul class="space-y-2">
							<li v-for="i in r.top_items" :key="i.item_code">
								<div class="flex justify-between gap-3 text-sm">
									<span class="truncate">{{ i.item_name || i.item_code }}</span>
									<span class="shrink-0 tabular">{{ compactMoney(i.amount, r.currency) }}
										<span class="text-gray-500">· {{ qty(i.qty) }} {{ i.uom }} in {{ i.quotes }} quote{{ i.quotes === 1 ? "" : "s" }}</span></span>
								</div>
								<div class="mt-1 h-1.5 rounded-full bg-gray-100">
									<div class="h-1.5 rounded-full bg-gray-400" :style="{ width: pct(i.amount, maxItem) + '%' }" />
								</div>
							</li>
							<li v-if="!r.top_items?.length" class="text-sm text-gray-500">None yet.</li>
						</ul>
					</div>
				</div>

				<!-- team: one row per seller -->
				<div v-if="r.by_seller">
					<h3 class="mb-2 text-sm font-medium text-gray-700">By seller</h3>
					<div class="overflow-x-auto">
						<table class="w-full min-w-[560px] text-sm">
							<thead class="text-left text-xs uppercase tracking-wide text-gray-500">
								<tr class="border-b">
									<th class="py-2 pr-3 font-medium">Seller</th>
									<th class="py-2 px-3 text-right font-medium">Quotes</th>
									<th class="py-2 px-3 text-right font-medium">Quoted</th>
									<th class="py-2 px-3 text-right font-medium">Won</th>
									<th class="py-2 px-3 text-right font-medium">Win rate</th>
									<th v-if="r.can['Sales Invoice']" class="py-2 pl-3 text-right font-medium">Invoiced</th>
								</tr>
							</thead>
							<tbody class="divide-y">
								<tr v-for="s in r.by_seller" :key="s.user">
									<td class="py-2 pr-3">{{ s.name }}</td>
									<td class="py-2 px-3 text-right tabular">{{ s.quotes }}</td>
									<td class="py-2 px-3 text-right tabular">{{ compactMoney(s.quoted, r.currency) }}</td>
									<td class="py-2 px-3 text-right tabular">{{ compactMoney(s.won, r.currency) }}</td>
									<td class="py-2 px-3 text-right tabular">{{ s.win_rate == null ? "–" : s.win_rate + "%" }}</td>
									<td v-if="r.can['Sales Invoice']" class="py-2 pl-3 text-right tabular">{{ compactMoney(s.invoiced, r.currency) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</template>

			<!-- full desk reports (the Reports page lists them all itself) -->
			<div v-if="r.reports?.length && !hideReports">
				<div class="mb-2 flex items-baseline justify-between gap-3">
					<h3 class="text-sm font-medium text-gray-700">Full reports</h3>
					<router-link to="/reports" class="text-sm text-blue-700 hover:underline">All reports →</router-link>
				</div>
				<div class="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
					<a v-for="rep in r.reports" :key="rep.name" :href="rep.url" target="_blank" rel="noopener"
						class="rounded-md border px-3 py-2 hover:border-gray-400">
						<div class="text-sm font-medium">{{ rep.name }} ↗</div>
						<div class="text-xs text-gray-500">{{ rep.description }}</div>
					</a>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup>
import { computed, ref } from "vue"
import { boot } from "@/boot"

defineProps({ hideReports: Boolean })
import { api, errorMessages } from "@/utils/api"
import { money, compactMoney } from "@/utils/format"
import BarChart from "@/components/BarChart.vue"

const SCOPES = [{ value: "me", label: "Me" }, { value: "team", label: "Team" }]
const KEY = "sales.report.scope"

const r = ref(null)
const loading = ref(false)
const error = ref("")
const scope = ref(boot.is_sales_manager ? read() || "me" : "me")

function read() {
	try { return localStorage.getItem(KEY) } catch { return null }
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		r.value = await api("get_my_report", { scope: scope.value })
	} catch (e) {
		error.value = errorMessages(e).join(" ")
	} finally {
		loading.value = false
	}
}

function setScope(v) {
	if (v === scope.value) return
	scope.value = v
	try { localStorage.setItem(KEY, v) } catch {}
	load()
}

const title = computed(() => (scope.value === "team" ? "Team sales" : "My sales"))
const q = computed(() => r.value?.quotes)
const empty = computed(() => r.value && !r.value.year_to_date?.quoted?.count && !r.value.year_to_date?.ordered?.count)

// only the series the user can read
const series = computed(() => [
	{ key: "quoted", label: "Quoted", class: "fill-gray-300", swatch: "bg-gray-300", dt: "Quotation" },
	{ key: "ordered", label: "Ordered", class: "fill-blue-500", swatch: "bg-blue-500", dt: "Sales Order" },
	{ key: "invoiced", label: "Invoiced", class: "fill-green-500", swatch: "bg-green-500", dt: "Sales Invoice" },
].filter((s) => r.value?.can[s.dt]))

const figures = computed(() => {
	const m = r.value?.this_month || {}, y = r.value?.year_to_date || {}, c = r.value?.currency
	const n = (t, word) => `${t?.count || 0} ${word}${t?.count === 1 ? "" : "s"}`
	const out = []
	if (m.quoted) out.push({ label: "Quoted this month", value: compactMoney(m.quoted.total, c), hint: n(m.quoted, "quotation") })
	if (m.ordered) out.push({ label: "Ordered this month", value: compactMoney(m.ordered.total, c), hint: n(m.ordered, "sales order") })
	if (y.invoiced) out.push({ label: "Invoiced this year", value: compactMoney(y.invoiced.total, c), hint: n(y.invoiced, "invoice") })
	else if (y.ordered) out.push({ label: "Ordered this year", value: compactMoney(y.ordered.total, c), hint: n(y.ordered, "sales order") })
	if (q.value) out.push({
		label: "Win rate",
		value: q.value.win_rate == null ? "–" : `${q.value.win_rate}%`,
		hint: q.value.decided ? `${q.value.won.count} won of ${q.value.decided} decided` : "No quotation decided yet",
	})
	return out
})

const outcomes = computed(() => q.value ? [
	{ key: "won", label: "Won", bar: "bg-blue-500", ...q.value.won },
	{ key: "open", label: "Still open", bar: "bg-gray-400", ...q.value.open },
	{ key: "lost", label: "Lost", bar: "bg-red-400", ...q.value.lost },
	{ key: "expired", label: "Expired", bar: "bg-amber-300", ...q.value.expired },
] : [])
const share = (n) => { const all = outcomes.value.reduce((a, o) => a + o.count, 0); return all ? (n / all) * 100 : 0 }

const pct = (v, max) => (max ? Math.max(0, Math.min(100, (v / max) * 100)) : 0)
const maxCustomer = computed(() => Math.max(0, ...(r.value?.top_customers || []).map((c) => c.quoted)))
const maxItem = computed(() => Math.max(0, ...(r.value?.top_items || []).map((i) => i.amount)))
const qty = (v) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })

load()
</script>
