<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Petty cash" subtitle="Cash boxes on a float: spend with a receipt, top up from the bank, count the cash">
			<Button v-if="box" variant="solid" icon-left="plus" label="New voucher" @click="openVoucher" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<Empty v-else-if="!data.boxes.length" icon="dollar-sign">
				No petty cash boxes yet.<template v-if="boot.is_settings_manager"> Add one under <router-link to="/settings" class="text-blue-700 hover:underline">Settings → Petty cash</router-link>.</template>
			</Empty>

			<template v-else>
				<!-- Boxes -->
				<div class="flex gap-3 overflow-x-auto hide-scrollbar">
					<button v-for="b in data.boxes" :key="b.account" class="w-72 shrink-0 rounded-lg border bg-white p-4 text-left"
						:class="b.account === current ? 'border-gray-900 ring-1 ring-gray-900' : 'hover:border-gray-400'" @click="pick(b.account)">
						<div class="flex items-center justify-between gap-2">
							<span class="truncate font-medium">{{ b.name }}</span>
							<span class="rounded bg-gray-100 px-1.5 text-xs text-gray-600">{{ b.currency }}</span>
						</div>
						<div class="mt-2 flex items-baseline justify-between gap-2">
							<span class="text-xl font-semibold tabular" :class="low(b) ? 'text-amber-700' : ''">{{ cur(b.balance, b.currency) }}</span>
							<span class="text-xs text-gray-500">of {{ b.float_amount ? cur(b.float_amount, b.currency) : "no float set" }}</span>
						</div>
						<div class="mt-1.5 h-1.5 rounded bg-gray-100">
							<div class="h-1.5 rounded" :class="low(b) ? 'bg-amber-500' : 'bg-green-500'" :style="{ width: `${fill(b)}%` }" />
						</div>
						<div class="mt-2 space-y-0.5 text-xs text-gray-500">
							<div>{{ b.custodian_name ? `Kept by ${b.custodian_name}` : "No custodian set" }}</div>
							<div>Spent {{ cur(b.spent_since_top_up, b.currency) }} {{ b.last_top_up ? `since the ${date(b.last_top_up)} top-up` : "so far" }}</div>
							<div v-if="b.awaiting" class="font-medium text-amber-700">{{ b.awaiting }} awaiting approval</div>
						</div>
					</button>
				</div>

				<!-- The box -->
				<section v-if="box" class="rounded-lg border bg-white">
					<header class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
						<Chips v-model="status" :options="STATUSES" />
						<div v-if="data.can_manage" class="flex gap-2">
							<Button icon-left="arrow-down-circle" label="Top up" @click="openTopUp" />
							<Button icon-left="check-square" label="Count cash" @click="openCount" />
						</div>
					</header>
					<p v-if="box.last_count" class="border-b bg-gray-50 px-4 py-2 text-xs text-gray-600">
						Last count {{ relative(box.last_count.creation) }}: {{ box.last_count.content.replace(/^Cash count:\s*/, "") }}
					</p>
					<div v-if="!vouchers" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<Empty v-else-if="!vouchers.length" icon="file-text">Nothing here yet.</Empty>
					<div v-for="v in vouchers || []" :key="v.name" class="flex flex-wrap items-start gap-3 border-t px-4 py-3 first-of-type:border-t-0 sm:flex-nowrap">
						<div class="w-14 shrink-0 text-xs text-gray-500">{{ shortDate(v.posting_date) }}</div>
						<div class="min-w-0 flex-1">
							<div class="truncate text-sm font-medium" :class="v.status === 'cancelled' ? 'text-gray-400 line-through' : ''">
								{{ v.kind === "top_up" ? "Top-up from the bank" : v.kind === "count" ? "Cash count difference" : v.paid_to || v.remark || v.name }}
							</div>
							<div class="flex flex-wrap gap-x-2 text-xs text-gray-500">
								<span v-if="v.kind === 'voucher'">{{ v.remark && v.remark !== v.paid_to ? v.remark : accountName(v.other) }}</span>
								<span>{{ v.kind === "voucher" ? "· " : "" }}{{ v.by }}</span>
								<a v-if="v.receipt" :href="v.receipt.file_url" target="_blank" class="text-blue-700 hover:underline">· receipt</a>
							</div>
						</div>
						<div class="shrink-0 text-right">
							<div class="text-sm font-medium tabular" :class="v.money_in ? 'text-green-700' : ''">{{ v.money_in ? "+" : "−" }}{{ cur(v.amount, box.currency) }}</div>
							<span class="mt-0.5 inline-block rounded px-1.5 text-xs" :class="STATUS_STYLE[v.status]">{{ STATUS_LABEL[v.status] }}</span>
						</div>
						<div v-if="v.status === 'awaiting' && data.can_approve" class="flex w-full justify-end gap-2 sm:w-auto">
							<Button size="sm" variant="solid" label="Approve" :loading="busy === v.name" @click="approve(v)" />
							<Button size="sm" theme="red" label="Decline" @click="startDecline(v)" />
						</div>
					</div>
					<div v-if="vouchers && vouchers.length >= 50 * pages" class="border-t p-3 text-center">
						<Button label="Load more" @click="loadVouchers(true)" />
					</div>
				</section>
			</template>
		</div>

		<!-- New voucher -->
		<Dialog v-model="voucherOpen" :options="{ title: `Petty cash voucher · ${box?.name || ''}`, size: 'lg' }">
			<template #body-content>
				<div class="space-y-3">
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Paid to <span class="text-red-500">*</span></span>
							<input v-model="v.paid_to" class="form-input w-full" placeholder="e.g. TM Pick n Pay, courier" /></label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">What for (account) <span class="text-red-500">*</span></span>
							<LinkField v-model="v.expense_account" doctype="Account" :method="SEARCH" placeholder="e.g. Office supplies" /></label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Date</span><input v-model="v.date" type="date" class="form-input w-full" /></label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Amount ({{ box?.currency }}) <span class="text-red-500">*</span></span>
							<input v-model.number="v.amount" type="number" step="0.01" min="0" class="form-input w-full text-right tabular" /></label>
						<label class="block sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Note</span>
							<input v-model="v.remark" class="form-input w-full" placeholder="e.g. milk and sugar for the office" /></label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">VAT included</span>
							<LinkField v-model="v.vat" doctype="Purchase Taxes and Charges Template" :method="SEARCH" placeholder="No VAT" /></label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Receipt</span>
							<input type="file" accept=".pdf,image/*" capture="environment" class="block w-full text-sm" @change="v.file = $event.target.files[0]" /></label>
					</div>
					<p v-if="overLimit" class="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
						Over this box's {{ cur(box.approval_limit, box.currency) }} limit — it waits for an Accounts Manager to approve before it's posted.
					</p>
					<p v-else-if="Number(v.amount) > box?.balance" class="text-sm text-amber-700">That's more than the {{ cur(box.balance, box.currency) }} in the box.</p>
				</div>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" :label="overLimit ? 'Send for approval' : 'Record voucher'" :disabled="!voucherReady" :loading="saving" @click="saveVoucher" />
			</template>
		</Dialog>

		<!-- Top up -->
		<Dialog v-model="topUpOpen" :options="{ title: `Top up ${box?.name || ''}`, size: 'md' }">
			<template #body-content>
				<div class="space-y-3">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">From</span>
						<select v-model="t.bank" class="form-select w-full">
							<option v-for="b in boot.banks" :key="b.name" :value="b.name">{{ b.account_name || b.name }} ({{ b.currency }})</option>
						</select></label>
					<div class="grid grid-cols-2 gap-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">Date</span><input v-model="t.date" type="date" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Amount ({{ topUpCurrency }})</span>
							<input v-model.number="t.amount" type="number" step="0.01" class="form-input w-full text-right tabular" :placeholder="suggested" /></label>
					</div>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Reference</span>
						<input v-model="t.reference" class="form-input w-full" placeholder="Cheque or transfer reference" /></label>
					<p class="text-xs text-gray-500">Left empty, the amount brings the box back to its {{ cur(box?.float_amount, box?.currency) }} float. When it shows on the bank statement, Bank suggests it as the match.</p>
				</div>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" label="Top up" :loading="saving" @click="saveTopUp" />
			</template>
		</Dialog>

		<!-- Count -->
		<Dialog v-model="countOpen" :options="{ title: `Count ${box?.name || ''}`, size: 'sm' }">
			<template #body-content>
				<div class="space-y-3">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Cash in the box ({{ box?.currency }})</span>
						<input v-model.number="c.counted" type="number" step="0.01" class="form-input w-full text-right tabular" /></label>
					<p v-if="c.counted !== null && c.counted !== ''" class="text-sm" :class="countDiff ? 'text-amber-700' : 'text-green-700'">
						{{ countDiff ? `${countDiff < 0 ? "Short" : "Over"} by ${cur(Math.abs(countDiff), box.currency)} — posted to cash over / short.` : "Matches the books." }}
					</p>
					<p v-else class="text-xs text-gray-500">The books say {{ cur(box?.balance, box?.currency) }}.</p>
				</div>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" label="Record count" :disabled="c.counted === null || c.counted === ''" :loading="saving" @click="saveCount" />
			</template>
		</Dialog>

		<!-- Decline -->
		<Dialog v-model="declineOpen" :options="{ title: `Decline ${declining?.paid_to || declining?.name || ''}?`, size: 'sm' }">
			<template #body-content>
				<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Why (the custodian sees this)</span>
					<input v-model="declineReason" class="form-input w-full" placeholder="e.g. no receipt" /></label>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" theme="red" label="Decline" :disabled="!declineReason.trim()" :loading="saving" @click="decline" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Dialog, LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import { date, relative, today } from "@/utils/format"
import { acc, cur, ok, fail } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import Empty from "@/hr/components/Empty.vue"

const SEARCH = "erp_overrides.api.accounts.petty_search"
const STATUSES = [{ value: "", label: "All" }, { value: "posted", label: "Posted" }, { value: "awaiting", label: "Awaiting approval" }]
const STATUS_LABEL = { posted: "Posted", awaiting: "Awaiting approval", cancelled: "Cancelled" }
const STATUS_STYLE = { posted: "bg-green-50 text-green-800", awaiting: "bg-amber-50 text-amber-800", cancelled: "bg-gray-100 text-gray-500" }

const route = useRoute()
const router = useRouter()
const data = ref(null)
const current = ref(route.query.box || null)
const status = ref("")
const vouchers = ref(null)
const pages = ref(1)
const saving = ref(false)
const busy = ref(null)

const box = computed(() => data.value?.boxes.find((b) => b.account === current.value))
const fill = (b) => (b.float_amount ? Math.max(0, Math.min(100, (b.balance / b.float_amount) * 100)) : 0)
const low = (b) => b.float_amount && b.balance < 0.2 * b.float_amount
const shortDate = (d) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })
const accountName = (a) => String(a || "").replace(/^\d+\s*-\s*/, "").replace(/\s*-\s*[A-Z]{1,4}$/, "")

async function load() {
	try {
		data.value = await acc("get_petty_cash")
		if (!box.value) current.value = data.value.boxes.find((b) => b.mine)?.account || data.value.boxes[0]?.account || null
	} catch (e) {
		fail(e, "Could not load petty cash")
	}
}

async function loadVouchers(more = false) {
	if (!current.value) return
	if (!more) {
		vouchers.value = null
		pages.value = 1
	}
	try {
		const rows = await acc("get_vouchers", { account: current.value, status: status.value || undefined, start: more ? vouchers.value.length : 0 })
		vouchers.value = more ? [...vouchers.value, ...rows] : rows
		if (more) pages.value++
	} catch (e) {
		vouchers.value = []
		fail(e)
	}
}

function pick(account) {
	current.value = account
	router.replace({ query: { box: account } })
}

async function refresh() {
	await load()
	await loadVouchers()
}

// ── New voucher ──
const voucherOpen = ref(false)
const v = reactive({})
const overLimit = computed(() => box.value?.approval_limit && Number(v.amount) > box.value.approval_limit)
const voucherReady = computed(() => v.paid_to && v.expense_account && Number(v.amount) > 0)

function openVoucher() {
	Object.assign(v, { paid_to: "", expense_account: "", date: today(), amount: null, remark: "", vat: "", file: null })
	voucherOpen.value = true
}

async function upload(file) {
	if (!file) return undefined
	const fd = new FormData()
	fd.append("file", file, file.name)
	fd.append("is_private", "1")
	const res = await fetch("/api/method/upload_file", { method: "POST", body: fd, headers: { "X-Frappe-CSRF-Token": window.csrf_token } })
	if (!res.ok) throw { messages: ["Could not upload the receipt"] }
	return (await res.json()).message.file_url
}

async function saveVoucher() {
	saving.value = true
	try {
		const out = await acc("new_voucher", {
			account: current.value, posting_date: v.date, amount: v.amount, paid_to: v.paid_to, expense_account: v.expense_account,
			remark: v.remark || undefined, vat_template: v.vat || undefined, file_url: await upload(v.file),
		})
		ok(out.status === "awaiting" ? "Sent for approval" : "Voucher recorded", out.name)
		voucherOpen.value = false
		await refresh()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

// ── Top up ──
const topUpOpen = ref(false)
const t = reactive({})
const topUpCurrency = computed(() => boot.banks?.find((b) => b.name === t.bank)?.currency)
const suggested = computed(() => (box.value && box.value.float_amount > box.value.balance && topUpCurrency.value === box.value.currency
	? (box.value.float_amount - box.value.balance).toFixed(2) : ""))

function openTopUp() {
	Object.assign(t, { bank: boot.banks?.find((b) => b.currency === box.value.currency)?.name || boot.banks?.[0]?.name, date: today(), amount: null, reference: "" })
	topUpOpen.value = true
}

async function saveTopUp() {
	saving.value = true
	try {
		const out = await acc("top_up", { account: current.value, bank_account: t.bank, posting_date: t.date, amount: t.amount || undefined, reference_no: t.reference || undefined })
		ok("Topped up", `${cur(out.amount, out.currency)} · ${out.name}`)
		topUpOpen.value = false
		await refresh()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

// ── Count ──
const countOpen = ref(false)
const c = reactive({ counted: null })
const countDiff = computed(() => Number((Number(c.counted) - (box.value?.balance || 0)).toFixed(2)))

function openCount() {
	c.counted = null
	countOpen.value = true
}

async function saveCount() {
	saving.value = true
	try {
		const out = await acc("count_cash", { account: current.value, counted: c.counted, posting_date: today() })
		ok(out.difference ? "Count recorded, difference posted" : "Count recorded — it matches", out.journal_entry || "")
		countOpen.value = false
		await refresh()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

// ── Approve / decline ──
const declineOpen = ref(false)
const declining = ref(null)
const declineReason = ref("")

async function approve(row) {
	busy.value = row.name
	try {
		await acc("approve_voucher", { name: row.name })
		ok("Approved and posted", row.name)
		await refresh()
	} catch (e) {
		fail(e)
	} finally {
		busy.value = null
	}
}

function startDecline(row) {
	declining.value = row
	declineReason.value = ""
	declineOpen.value = true
}

async function decline() {
	saving.value = true
	try {
		await acc("decline_voucher", { name: declining.value.name, reason: declineReason.value })
		ok("Declined", declining.value.name)
		declineOpen.value = false
		await refresh()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

watch([current, status], () => loadVouchers())
load()
</script>
