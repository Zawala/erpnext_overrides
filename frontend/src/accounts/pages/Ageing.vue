<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="isCustomer ? 'Owed to us' : 'We owe'"
			:subtitle="isCustomer ? 'Open customer invoices by how late they are' : 'Open supplier bills by how late they are'">
			<Button v-if="!isCustomer" variant="solid" icon-left="plus" label="New bill" @click="$router.push('/payables/new-bill')" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<template v-else>
				<!-- Orders to bill: received on a purchase order, not yet billed (three-way match) -->
				<section v-if="!isCustomer && orders" class="rounded-lg border bg-white">
					<header class="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
						<h3 class="font-semibold">Orders to bill</h3>
						<span class="text-xs text-gray-500">Received against a purchase order, waiting for the supplier's invoice<template v-if="orders.waiting"> · {{ orders.waiting }} more not received yet</template></span>
					</header>
					<p v-if="!orders.rows.length" class="px-4 py-3 text-sm text-gray-500">Nothing received is waiting to be billed.</p>
					<div v-for="o in orders.rows" :key="o.name" class="flex flex-wrap items-center gap-3 border-t px-4 py-2.5 text-sm first-of-type:border-t-0">
						<div class="min-w-0 flex-1">
							<div class="truncate font-medium">{{ o.supplier_name || o.supplier }}</div>
							<div class="text-xs text-gray-500">{{ o.name }} · {{ date(o.transaction_date) }} · {{ Math.round(o.per_received) }}% received, {{ Math.round(o.per_billed) }}% billed</div>
						</div>
						<span class="tabular">{{ cur(o.to_bill, o.currency) }}</span>
						<Button size="sm" variant="solid" label="Bill this order" :loading="billing === o.name" @click="billOrder(o)" />
					</div>
				</section>

				<!-- Totals per currency -->
				<section v-for="(t, currency) in data.totals" :key="currency" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
					<div class="rounded-lg border border-gray-900 bg-white px-4 py-3">
						<div class="text-xs text-gray-500">Total {{ currency }}</div>
						<div class="text-xl font-semibold tabular">{{ cur(t.total, currency) }}</div>
					</div>
					<div v-for="b in data.buckets" :key="b" class="rounded-lg border bg-white px-4 py-3">
						<div class="text-xs text-gray-500">{{ b === "Not due" ? "Not due yet" : `${b} days late` }}</div>
						<div class="text-lg font-semibold tabular" :class="b === '90+' && t[b] ? 'text-red-700' : ''">{{ cur(t[b], currency) }}</div>
					</div>
				</section>
				<Empty v-if="!data.rows.length" icon="check-circle">{{ isCustomer ? "Nobody owes us anything." : "We owe nobody anything." }}</Empty>

				<!-- Per party -->
				<div v-else class="overflow-x-auto rounded-lg border bg-white">
					<table class="w-full text-sm tabular">
						<thead class="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
							<tr>
								<th class="px-4 py-2 text-left font-medium">{{ isCustomer ? "Customer" : "Supplier" }}</th>
								<th v-for="b in data.buckets" :key="b" class="whitespace-nowrap px-3 py-2 text-right font-medium">{{ b }}</th>
								<th class="px-4 py-2 text-right font-medium">Total</th>
							</tr>
						</thead>
						<tbody>
							<template v-for="p in data.rows" :key="p.party + p.currency">
								<tr class="cursor-pointer border-t hover:bg-gray-50" @click="toggle(p)">
									<td class="px-4 py-2">
										<div class="font-medium">{{ p.party_name }}</div>
										<div class="text-xs text-gray-500">{{ p.invoices }} invoice{{ p.invoices === 1 ? "" : "s" }} · {{ p.currency }}</div>
									</td>
									<td v-for="b in data.buckets" :key="b" class="px-3 py-2 text-right" :class="b === '90+' && p[b] ? 'text-red-700' : p[b] ? '' : 'text-gray-300'">
										{{ p[b] ? num(p[b]) : "—" }}
									</td>
									<td class="px-4 py-2 text-right font-semibold">{{ num(p.total) }}</td>
								</tr>
								<tr v-if="openParty === p.party" class="border-t bg-gray-50/60">
									<td :colspan="data.buckets.length + 2" class="px-4 py-2">
										<div v-if="!invoices" class="py-2"><LoadingIndicator class="h-4 w-4 text-gray-500" /></div>
										<div v-for="inv in invoices || []" :key="inv.name" class="flex flex-wrap items-center gap-3 py-1.5">
											<router-link v-if="recordRoute(inv.doctype, inv.name)" :to="recordRoute(inv.doctype, inv.name)" class="w-44 font-medium hover:underline">{{ inv.name }}</router-link>
											<a v-else :href="deskUrl(inv.doctype, inv.name)" target="_blank" class="w-44 font-medium hover:underline">{{ inv.name }}</a>
											<span class="w-36 text-gray-500">due {{ date(inv.due_date) }}</span>
											<span class="w-24 text-xs" :class="inv.bucket === 'Not due' ? 'text-gray-500' : 'text-amber-700'">{{ inv.bucket === "Not due" ? "not due" : `${inv.bucket} late` }}</span>
											<span v-if="inv.match" class="rounded px-1.5 py-0.5 text-xs" :class="MATCH_THEME[inv.match.status]" :title="inv.match.message">{{ inv.match.label }}</span>
											<span class="flex-1 text-right">{{ cur(inv.outstanding_amount, inv.currency) }}</span>
											<Button size="sm" :label="isCustomer ? 'Receive' : 'Pay'" :disabled="inv.match && !inv.match.payable"
												:title="inv.match && !inv.match.payable ? `Can't pay yet: ${inv.match.message}` : ''" @click="startPay(inv)" />
										</div>
									</td>
								</tr>
							</template>
						</tbody>
					</table>
				</div>
			</template>
		</div>

		<Dialog v-model="payOpen" :options="{ title: `${isCustomer ? 'Receive payment for' : 'Pay'} ${pay.invoice?.name || ''}`, size: 'md' }">
			<template #body-content>
				<div class="space-y-3">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">{{ isCustomer ? "Into" : "From" }}</span>
						<select v-model="pay.bank" class="form-select w-full">
							<option v-for="b in boot.banks" :key="b.name" :value="b.name">{{ b.account_name || b.name }} ({{ b.currency }})</option>
						</select></label>
					<div class="grid grid-cols-2 gap-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">Date</span><input v-model="pay.date" type="date" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Amount ({{ bankCurrency }})</span>
							<input v-model.number="pay.amount" type="number" step="0.01" class="form-input w-full text-right tabular" /></label>
					</div>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Reference</span>
						<input v-model="pay.reference" class="form-input w-full" placeholder="Bank reference or cheque number" /></label>
					<p class="text-xs text-gray-500">When it shows on the bank statement, Bank will suggest this payment as the match.</p>
				</div>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" :label="isCustomer ? 'Record receipt' : 'Record payment'" :loading="paying" @click="recordPay" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { Dialog, LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import { date, today } from "@/utils/format"
import { acc, cur, ok, fail, deskUrl } from "../api"
import { recordRoute, MATCH_THEME } from "../records"
import { useRouter } from "vue-router"
import PageHeader from "@/hr/components/PageHeader.vue"
import Empty from "@/hr/components/Empty.vue"

const props = defineProps({ partyType: String })
const router = useRouter()
const orders = ref(null)
const billing = ref(null)
const isCustomer = computed(() => props.partyType === "Customer")
const data = ref(null)
const openParty = ref(null)
const invoices = ref(null)
const payOpen = ref(false)
const paying = ref(false)
const pay = reactive({ invoice: null, bank: "", date: today(), amount: 0, reference: "" })
const bankCurrency = computed(() => boot.banks?.find((b) => b.name === pay.bank)?.currency)

const num = (v) => Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

async function load() {
	data.value = null
	orders.value = null
	try {
		if (props.partyType === "Supplier") acc("get_orders_to_bill").then((o) => (orders.value = o)).catch(() => {})
		data.value = await acc("get_ageing", { party_type: props.partyType })
	} catch (e) {
		fail(e)
	}
}

async function toggle(p) {
	if (openParty.value === p.party) return (openParty.value = null)
	openParty.value = p.party
	invoices.value = null
	invoices.value = await acc("get_open_invoices", { party_type: props.partyType, party: p.party })
}

async function billOrder(o) {
	billing.value = o.name
	try {
		const name = await acc("bill_order", { purchase_order: o.name })
		ok("Draft bill made", `${name}: add the supplier's invoice number and date, attach it, then submit`)
		router.push(recordRoute("Purchase Invoice", name))
	} catch (e) {
		fail(e)
	} finally {
		billing.value = null
	}
}

function startPay(inv) {
	Object.assign(pay, { invoice: inv, date: today(), reference: "",
		bank: boot.banks?.find((b) => b.currency === inv.currency)?.name || boot.banks?.[0]?.name, amount: inv.outstanding_amount })
	payOpen.value = true
}

async function recordPay() {
	paying.value = true
	try {
		const name = await acc("record_payment", { doctype: pay.invoice.doctype, invoice: pay.invoice.name, bank_account: pay.bank,
			amount: pay.amount, posting_date: pay.date, reference_no: pay.reference || undefined })
		ok(isCustomer.value ? "Receipt recorded" : "Payment recorded", name)
		payOpen.value = false
		openParty.value = null
		await load()
	} catch (e) {
		fail(e)
	} finally {
		paying.value = false
	}
}

watch(() => props.partyType, load, { immediate: true })
</script>
