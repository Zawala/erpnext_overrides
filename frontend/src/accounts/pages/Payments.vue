<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Payments" subtitle="Every payment in and out of the banks, and whether the bank statement has caught up with it">
			<Button variant="solid" icon-left="send" label="Make a payment" @click="paying = true" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<!-- Filters -->
			<div class="space-y-3 rounded-lg border bg-white p-3">
				<div class="flex flex-wrap items-center gap-2">
					<Chips v-model="f.direction" :options="DIRECTIONS" />
					<span class="hidden h-5 border-l sm:block" />
					<Chips v-model="f.status" :options="STATUSES" />
				</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_14rem_9.5rem_9.5rem_auto]">
					<input v-model="f.search" type="search" class="form-input col-span-2 min-w-0 sm:col-span-1" placeholder="Search who, reference, what for or amount" />
					<select v-model="f.account" class="form-select col-span-2 min-w-0 sm:col-span-1" aria-label="Bank account">
						<option value="">All bank accounts</option>
						<option v-for="b in boot.banks" :key="b.account" :value="b.account">{{ b.account_name || b.name }} ({{ b.currency }})</option>
						<option v-for="c in boot.cash_accounts" :key="c.account" :value="c.account">{{ c.account_name }} — cash ({{ c.currency }})</option>
					</select>
					<input v-model="f.from" type="date" class="form-input min-w-0" aria-label="From" />
					<input v-model="f.to" type="date" class="form-input min-w-0" aria-label="To" />
					<label class="col-span-2 flex items-center gap-2 whitespace-nowrap text-sm text-gray-700 sm:col-span-1">
						<input v-model="f.mine" type="checkbox" class="form-checkbox" /> Made by me
					</label>
				</div>
			</div>

			<!-- Totals per currency -->
			<div v-if="data && Object.keys(data.totals).length" class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<template v-for="(t, currency) in data.totals" :key="currency">
					<div class="rounded-lg border bg-white px-4 py-3">
						<div class="text-xs text-gray-500">{{ f.status === "cancelled" ? "Cancelled" : f.direction === "in" ? "Received" : f.direction === "transfer" ? "Transferred" : f.direction === "out" ? "Paid out" : "In − out" }} · {{ currency }}</div>
						<div class="text-xl font-semibold tabular">{{ cur(headline(t), currency) }}</div>
						<div class="text-xs text-gray-500">{{ t.count }} payment{{ t.count === 1 ? "" : "s" }}</div>
					</div>
					<div class="rounded-lg border bg-white px-4 py-3" :class="t.waiting ? 'border-amber-200' : ''">
						<div class="text-xs text-gray-500">Waiting for the statement · {{ currency }}</div>
						<div class="text-xl font-semibold tabular">{{ cur(t.waiting_amount, currency) }}</div>
						<div class="text-xs" :class="t.waiting ? 'text-amber-700' : 'text-gray-500'">{{ t.waiting ? `${t.waiting} not on a statement yet` : "all cleared" }}</div>
					</div>
				</template>
			</div>

			<!-- The list -->
			<div class="overflow-hidden rounded-lg border bg-white">
				<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<Empty v-else-if="!data.rows.length" icon="send">{{ filtered ? "No payments match." : "No payments yet." }}</Empty>
				<template v-else>
					<div v-for="r in data.rows" :key="r.doctype + r.name" class="border-t first:border-t-0">
						<button class="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-50" :class="openKey === key(r) ? 'bg-gray-50' : ''" @click="toggle(r)">
							<div class="w-14 shrink-0 text-xs text-gray-500">{{ shortDate(r.posting_date) }}</div>
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium" :class="r.status === 'cancelled' ? 'text-gray-400 line-through' : ''">{{ r.counterparty || r.remark || r.name }}</div>
								<div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-gray-500">
									<span>{{ r.account_name }}</span>
									<span v-if="r.reference">· {{ r.reference }}</span>
									<span class="hidden sm:inline">· {{ r.by }}</span>
								</div>
							</div>
							<div class="shrink-0 text-right">
								<div class="text-sm font-medium tabular" :class="r.direction === 'in' ? 'text-green-700' : ''">
									{{ r.direction === "in" ? "+" : r.direction === "out" ? "−" : "" }}{{ cur(r.amount, r.currency) }}</div>
								<span class="mt-0.5 inline-block rounded px-1.5 text-xs" :class="STATUS_STYLE[r.status]">{{ STATUS_LABEL[r.status] }}</span>
							</div>
						</button>

						<!-- Detail -->
						<div v-if="openKey === key(r)" class="border-t bg-gray-50/60 px-4 py-3 text-sm sm:pl-[4.75rem]">
							<div v-if="!detail" class="py-2"><LoadingIndicator class="h-4 w-4 text-gray-500" /></div>
							<div v-else class="space-y-3">
								<div v-if="detail.paid.length">
									<div class="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Paid</div>
									<div v-for="p in detail.paid" :key="p.name" class="flex flex-wrap items-center gap-x-3">
										<router-link v-if="recordRoute(p.doctype, p.name)" :to="recordRoute(p.doctype, p.name)" class="font-medium hover:underline">{{ p.name }}</router-link>
										<a v-else :href="deskUrl(p.doctype, p.name)" target="_blank" class="font-medium hover:underline">{{ p.name }}</a>
										<span v-if="p.bill_no" class="text-gray-500">{{ p.bill_no }}</span>
										<span class="flex-1 text-right tabular">{{ cur(p.amount, detail.party_currency) }}</span>
									</div>
									<div v-if="detail.unallocated > 0.005" class="flex text-gray-500">
										<span class="flex-1">On account, for their next bill</span><span class="tabular">{{ cur(detail.unallocated, detail.party_currency) }}</span>
									</div>
								</div>
								<div v-else-if="detail.payment_type" class="text-gray-500">
									{{ detail.payment_type === "Internal Transfer" ? "Transfer between our accounts." : `On account for ${detail.party_name || detail.party || "—"}, not against a bill.` }}
								</div>
								<div v-if="detail.rows.length">
									<div class="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Posted to</div>
									<div v-for="(a, i) in detail.rows.filter((a) => a.account !== r.account)" :key="i" class="flex gap-3">
										<span class="min-w-0 flex-1 truncate">{{ a.party || a.account }}<span v-if="a.remark" class="text-gray-500"> · {{ a.remark }}</span></span>
										<span class="tabular">{{ cur(a.debit || a.credit, a.currency) }}</span>
									</div>
								</div>
								<div v-if="r.remark" class="text-gray-600">{{ r.remark }}</div>
								<div class="text-gray-600">
									<template v-if="detail.bank_line">
										<FeatherIcon name="check-circle" class="mr-1 inline h-4 w-4 text-green-600" />Cleared {{ date(detail.clearance_date) }} — on the statement
										<router-link :to="{ path: '/bank', query: { line: detail.bank_line.name } }" class="text-blue-700 hover:underline">{{ date(detail.bank_line.date) }}</router-link>.
									</template>
									<template v-else-if="r.status === 'cash'">
										<FeatherIcon name="dollar-sign" class="mr-1 inline h-4 w-4 text-blue-600" />Paid in cash — no bank statement to wait for.
									</template>
									<template v-else-if="detail.docstatus === 1">
										<FeatherIcon name="clock" class="mr-1 inline h-4 w-4 text-amber-600" />Not on a bank statement yet. When the line comes in, Bank suggests this payment as its match.
									</template>
									<template v-else>Cancelled.</template>
								</div>
								<div class="text-xs text-gray-500">{{ r.name }} · made by {{ detail.owner }} {{ relative(detail.creation) }}</div>
								<div class="flex flex-wrap gap-2">
									<Button size="sm" :icon-left="recordRoute(r.doctype, r.name) ? 'file-text' : 'external-link'"
										:label="recordRoute(r.doctype, r.name) ? 'Open' : 'Open in desk'" @click="openDesk(r)" />
									<Button size="sm" icon-left="printer" label="Print" @click="print(r)" />
									<Button v-if="detail.can_cancel" size="sm" theme="red" icon-left="x" label="Cancel payment" @click="cancelOpen = true" />
								</div>
							</div>
						</div>
					</div>
					<div v-if="data.rows.length < data.total" class="border-t p-3 text-center">
						<Button :label="`Load more (${data.total - data.rows.length})`" :loading="loading" @click="load(true)" />
					</div>
				</template>
			</div>
		</div>

		<PaymentDialog v-model="paying" @paid="load()" />

		<Dialog v-model="cancelOpen" :options="{ title: `Cancel ${openRow?.name || ''}?`, size: 'sm' }">
			<template #body-content>
				<p class="text-sm text-gray-700">The payment is reversed in the books{{ detail?.paid.length ? " and the bills it paid are open again" : "" }}. Use this for a payment made by mistake.</p>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" theme="red" label="Cancel payment" :loading="cancelling" @click="cancel" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Dialog, LoadingIndicator, debounce } from "frappe-ui"
import { boot } from "@/boot"
import { date, relative } from "@/utils/format"
import { acc, cur, ok, fail, deskUrl } from "../api"
import { recordRoute } from "../records"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import Empty from "@/hr/components/Empty.vue"
import PaymentDialog from "../components/PaymentDialog.vue"

const DIRECTIONS = [{ value: "out", label: "Paid out" }, { value: "in", label: "Received" }, { value: "transfer", label: "Transfers" }, { value: "", label: "All" }]
const STATUSES = [{ value: "", label: "Any status" }, { value: "waiting", label: "Waiting for the statement" }, { value: "cleared", label: "Cleared" }, { value: "cash", label: "Cash" }, { value: "cancelled", label: "Cancelled" }]
const STATUS_LABEL = { waiting: "Waiting", cleared: "Cleared", cash: "Cash", cancelled: "Cancelled" }
const STATUS_STYLE = { waiting: "bg-amber-50 text-amber-800", cleared: "bg-green-50 text-green-800", cash: "bg-blue-50 text-blue-800",
	cancelled: "bg-gray-100 text-gray-500" }

const route = useRoute()
const router = useRouter()
const f = reactive({ direction: "out", status: route.query.status || "", search: route.query.search || "", account: "", from: "", to: "", mine: false })
const data = ref(null)
const loading = ref(false)
const openKey = ref(null)
const openRow = ref(null)
const detail = ref(null)
const paying = ref(false)
const cancelOpen = ref(false)
const cancelling = ref(false)

const key = (r) => `${r.doctype}/${r.name}`
const filtered = computed(() => f.status || f.search || f.account || f.from || f.to || f.mine)
const shortDate = (d) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })
const headline = (t) => (f.direction === "in" ? t.in : f.direction === "transfer" ? t.transfer : f.direction === "out" ? t.out : t.in - t.out)

async function load(more = false) {
	loading.value = true
	try {
		const res = await acc("get_payments", {
			direction: f.direction, status: f.status || undefined, account: f.account || undefined, search: f.search || undefined,
			from_date: f.from || undefined, to_date: f.to || undefined, mine: f.mine ? 1 : 0, start: more ? data.value.rows.length : 0,
		})
		if (more) data.value.rows.push(...res.rows)
		else {
			data.value = res
			openKey.value = null
		}
	} catch (e) {
		fail(e, "Could not load payments")
	} finally {
		loading.value = false
	}
}

async function toggle(r) {
	if (openKey.value === key(r)) return (openKey.value = null)
	openKey.value = key(r)
	openRow.value = r
	detail.value = null
	try {
		detail.value = await acc("get_payment", { doctype: r.doctype, name: r.name })
	} catch (e) {
		fail(e)
	}
}

function openDesk(r) {
	const to = recordRoute(r.doctype, r.name)
	if (to) router.push(to)
	else window.open(deskUrl(r.doctype, r.name), "_blank")
}

function print(r) {
	window.open(`/printview?doctype=${encodeURIComponent(r.doctype)}&name=${encodeURIComponent(r.name)}&trigger_print=1`, "_blank")
}

async function cancel() {
	cancelling.value = true
	try {
		await acc("cancel_payment", { doctype: openRow.value.doctype, name: openRow.value.name })
		ok("Payment cancelled", openRow.value.name)
		cancelOpen.value = false
		await load()
	} catch (e) {
		fail(e)
	} finally {
		cancelling.value = false
	}
}

const reloadSoon = debounce(() => load(), 300)
watch(() => f.search, reloadSoon)
watch(() => [f.direction, f.status, f.account, f.from, f.to, f.mine], () => load())
load()
</script>
