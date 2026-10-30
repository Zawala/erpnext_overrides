<template>
	<div class="h-full overflow-y-auto">
		<header class="flex items-center gap-3 border-b bg-white px-4 lg:px-6 h-14 sticky top-0 z-10">
			<h1 class="flex-1 truncate text-lg font-semibold">{{ greeting }}, {{ firstName }}</h1>
			<Button icon-left="user-plus" label="New lead" class="hidden sm:inline-flex" @click="$router.push('/leads/new')" />
			<Button variant="solid" icon-left="file-text" label="New quotation" @click="$router.push('/quotations/new')" />
		</header>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-6">
			<!-- Approvals callout -->
			<router-link v-if="pipeline?.approvals" to="/approvals"
				class="flex items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 hover:bg-amber-100">
				<FeatherIcon name="alert-triangle" class="h-5 w-5 text-amber-600" />
				<div class="flex-1">
					<div class="font-medium text-amber-900">{{ pipeline.approvals }} sales order{{ pipeline.approvals > 1 ? "s" : "" }} waiting for your approval</div>
					<div class="text-sm text-amber-800">Sellers can't submit until you tick Credit / Discount Approved.</div>
				</div>
				<FeatherIcon name="chevron-right" class="h-5 w-5 text-amber-700" />
			</router-link>

			<!-- Pipeline -->
			<section v-for="lane in lanes" :key="lane.label">
				<h2 class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">{{ lane.label }}</h2>
				<div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
					<router-link v-for="s in lane.stages" :key="s.key" :to="s.to"
						class="group rounded-lg border bg-white p-4 hover:border-gray-400 transition-colors">
						<div class="text-sm text-gray-600">{{ s.label }}</div>
						<div class="mt-1 flex items-baseline gap-2">
							<span class="text-2xl font-semibold tabular">{{ s.count ?? "–" }}</span>
							<span v-if="s.total" class="text-sm text-gray-500 tabular">{{ compactMoney(s.total) }}</span>
						</div>
						<div v-if="s.hint" class="mt-1 text-xs text-gray-500 line-clamp-2">{{ s.hint }}</div>
					</router-link>
				</div>
			</section>

			<MySales v-if="can('Quotation') || can('Sales Order') || can('Sales Invoice')" />

			<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
				<!-- Expiring quotations -->
				<section class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h3 class="font-semibold">Quotations expiring soon</h3>
						<router-link :to="list('quotations', 'Open')" class="text-sm text-gray-500 hover:text-gray-900">All open →</router-link>
					</header>
					<ul class="divide-y">
						<li v-for="q in expiring" :key="q.name">
							<router-link :to="docRoute('Quotation', q.name)" class="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-gray-50">
								<div class="min-w-0">
									<div class="truncate font-medium">{{ q.customer_name || q.party_name }}</div>
									<div class="text-sm text-gray-500">{{ q.name }} · valid till {{ date(q.valid_till) }}</div>
								</div>
								<div class="shrink-0 font-medium tabular">{{ money(q.grand_total, q.currency) }}</div>
							</router-link>
						</li>
						<li v-if="!expiring.length" class="px-4 py-6 text-center text-sm text-gray-500">Nothing expiring in the next 14 days.</li>
					</ul>
				</section>

				<!-- My drafts -->
				<section class="rounded-lg border bg-white">
					<header class="border-b px-4 py-3"><h3 class="font-semibold">My drafts</h3></header>
					<ul class="divide-y">
						<li v-for="d in drafts" :key="d.doctype + d.name">
							<router-link :to="docRoute(d.doctype, d.name)" class="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-gray-50">
								<div class="min-w-0">
									<div class="truncate font-medium">{{ d.title }}</div>
									<div class="text-sm text-gray-500">{{ d.doctype }} · {{ d.name }} · {{ relative(d.modified) }}</div>
								</div>
								<div v-if="d.grand_total" class="shrink-0 font-medium tabular">{{ money(d.grand_total, d.currency) }}</div>
							</router-link>
						</li>
						<li v-if="!drafts.length" class="px-4 py-6 text-center text-sm text-gray-500">No drafts — nice.</li>
					</ul>
				</section>
			</div>

			<p class="text-center text-xs text-gray-400 pb-4">
				Convert first, then buy. A purchase order without a sales order behind it gets declined.
			</p>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { FeatherIcon, call } from "frappe-ui"
import { boot } from "@/boot"
import { doctypes, docRoute, can } from "@/doctypes"
import { api } from "@/utils/api"
import { money, compactMoney, date, relative, today, addDays } from "@/utils/format"
import { approvalCount } from "@/data/approvals"
import MySales from "@/components/MySales.vue"

const pipeline = ref(null)
const expiring = ref([])
const drafts = ref([])

const firstName = computed(() => (boot.full_name || "").split(" ")[0])
const greeting = computed(() => {
	const h = new Date().getHours()
	return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"
})

// pipeline stage → list page + filter chip
const list = (slug, f) => ({ path: `/${slug}`, query: { f } })
const LINKS = {
	leads: list("leads", "Open"),
	opportunities: list("opportunities", "Open"),
	quotations: list("quotations", "Open"),
	expiring: list("quotations", "Open"),
	draft_quotes: list("quotations", "Draft"),
	draft_orders: list("sales-orders", "Draft"),
	to_deliver: list("sales-orders", "To deliver & bill"),
	to_bill: list("sales-orders", "To deliver & bill"),
	dn_to_bill: list("delivery-notes", "To bill"),
	unpaid: list("sales-invoices", "Unpaid"),
	overdue: list("sales-invoices", "Overdue"),
	purchase_orders: list("purchase-orders", "To receive & bill"),
}
const SELLING = ["leads", "opportunities", "quotations", "expiring", "draft_quotes"]
const ORDERS = ["draft_orders", "to_deliver", "to_bill", "dn_to_bill", "unpaid", "overdue"]
const BUYING = ["purchase_orders"]

const lanes = computed(() => {
	const by = Object.fromEntries((pipeline.value?.stages || []).map((s) => [s.key, { ...s, to: LINKS[s.key] }]))
	// stages the user can't read are dropped server-side
	const pick = (keys) => (pipeline.value ? keys.filter((k) => by[k]).map((k) => by[k]) : keys.map((k) => ({ key: k, label: "…", to: LINKS[k] })))
	return [
		{ label: "Selling", stages: pick(SELLING) },
		{ label: "Orders, delivery & billing", stages: pick(ORDERS) },
		{ label: "Buying", stages: pick(BUYING) },
	].filter((l) => l.stages.length)
})

async function load() {
	const [p, e, ...d] = await Promise.all([
		api("get_pipeline"),
		call("frappe.client.get_list", {
			doctype: "Quotation",
			fields: ["name", "customer_name", "party_name", "grand_total", "currency", "valid_till"],
			filters: { docstatus: 1, status: ["in", ["Open", "Replied"]], valid_till: ["between", [today(), addDays(today(), 14)]] },
			order_by: "valid_till asc",
			limit_page_length: 8,
		}),
		...["Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "Purchase Order"].filter((dt) => can(dt)).map((dt) =>
			call("frappe.client.get_list", {
				doctype: dt,
				fields: doctypes[dt].listFields,
				filters: { docstatus: 0, owner: boot.user },
				order_by: "modified desc",
				limit_page_length: 5,
			}).then((rows) => rows.map((r) => ({ ...r, doctype: dt, title: doctypes[dt].title(r) })))
		),
	])
	pipeline.value = p
	approvalCount.value = p.approvals
	expiring.value = e
	drafts.value = d.flat().sort((a, b) => (a.modified < b.modified ? 1 : -1)).slice(0, 8)
}
load()
</script>
