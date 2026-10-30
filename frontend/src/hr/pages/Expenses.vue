<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Expenses" subtitle="Employee submits with the receipt → approver approves or reduces → finance posts and pays">
			<Button icon-left="list" label="All claims" @click="$router.push('/records/expense-claims')" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<Chips v-model="tab" :options="tabs" />

			<!-- Pending: the approver's queue, read-only here -->
			<section v-if="tab === 'pending'" class="rounded-lg border bg-white">
				<header class="flex items-center justify-between border-b px-4 py-3">
					<div>
						<h3 class="font-semibold">Waiting for an approver</h3>
						<p class="text-sm text-gray-500">Saved by the employee, not yet approved. Approve or reduce them in the Inbox.</p>
					</div>
					<Button variant="solid" label="Open inbox" @click="$router.push({ path: '/inbox' })" />
				</header>
				<ClaimTable :rows="pending" amount-key="total_claimed_amount" amount-label="Claimed" :loading="loading">
					<template #extra="{ row }">
						<span class="text-xs" :class="row.expense_approver ? 'text-gray-500' : 'text-red-600'">
							{{ row.expense_approver || "No approver" }}
						</span>
					</template>
				</ClaimTable>
			</section>

			<!-- Unpaid: approved, finance still to pay -->
			<section v-else class="rounded-lg border bg-white">
				<header class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
					<div>
						<h3 class="font-semibold">Approved, not yet paid</h3>
						<p class="text-sm text-gray-500">Run this before every payment run. Payment is made in desk.</p>
					</div>
					<div class="text-right">
						<div class="text-xs uppercase tracking-wide text-gray-500">Outstanding</div>
						<div class="text-xl font-semibold tabular">{{ money(unpaidTotal) }}</div>
					</div>
				</header>
				<ClaimTable :rows="unpaid" amount-key="outstanding" amount-label="Outstanding" :loading="loading">
					<template #extra="{ row }">
						<a :href="deskUrl('Expense Claim', row.name)" target="_blank" class="text-sm text-gray-700 underline">Pay in desk ↗</a>
					</template>
				</ClaimTable>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, h, ref, watch } from "vue"
import { useRoute, useRouter, RouterLink } from "vue-router"
import { LoadingIndicator, call } from "frappe-ui"
import { money, date } from "@/utils/format"
import { hr, fail, deskUrl } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"

const route = useRoute()
const router = useRouter()
const tab = ref(route.query.tab === "unpaid" ? "unpaid" : "pending")
watch(tab, (t) => router.replace({ query: { tab: t } }))

const pending = ref([])
const unpaid = ref([])
const loading = ref(true)
const unpaidTotal = computed(() => unpaid.value.reduce((s, r) => s + Number(r.outstanding || 0), 0))
const tabs = computed(() => [
	{ value: "pending", label: "Waiting for approval", count: pending.value.length },
	{ value: "unpaid", label: "To pay", count: unpaid.value.length },
])

const ClaimTable = (props, { slots }) => {
	if (props.loading) return h("div", { class: "p-10 text-center" }, h(LoadingIndicator, { class: "inline h-5 w-5 text-gray-500" }))
	if (!props.rows.length) return h("div", { class: "px-4 py-10 text-center text-gray-500" }, "Nothing here.")
	return h("ul", { class: "divide-y" }, props.rows.map((r) =>
		h("li", { class: "flex items-center gap-3 px-4 py-2.5" }, [
			h(RouterLink, { to: `/records/expense-claims/${encodeURIComponent(r.name)}`, class: "min-w-0 flex-1 hover:underline" }, () => [
				h("div", { class: "truncate font-medium" }, r.employee_name),
				h("div", { class: "text-sm text-gray-500" }, `${r.name} · ${date(r.posting_date)}`),
			]),
			slots.extra?.({ row: r }),
			h("div", { class: "w-32 shrink-0 text-right font-medium tabular" }, money(r[props.amountKey], r.currency)),
		])
	))
}
ClaimTable.props = ["rows", "amountKey", "amountLabel", "loading"]

async function load() {
	loading.value = true
	try {
		const [p, u] = await Promise.all([
			call("frappe.client.get_list", {
				doctype: "Expense Claim",
				fields: ["name", "employee_name", "posting_date", "total_claimed_amount", "currency", "expense_approver"],
				filters: { docstatus: 0, approval_status: "Draft" },
				order_by: "posting_date asc",
				limit_page_length: 200,
			}),
			hr("get_unpaid_claims"),
		])
		pending.value = p
		unpaid.value = u
	} catch (e) {
		fail(e, "Could not load claims")
	} finally {
		loading.value = false
	}
}
load()
</script>
