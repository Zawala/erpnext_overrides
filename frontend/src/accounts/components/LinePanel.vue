<template>
	<div v-if="!line" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
	<div v-else class="mx-auto w-full max-w-3xl space-y-4 p-4 lg:p-6">
		<!-- The statement line -->
		<header class="flex items-start gap-3">
			<button class="-ml-1 rounded p-1 text-gray-600 hover:bg-gray-100 lg:hidden" aria-label="Back to the list" @click="$emit('close')">
				<FeatherIcon name="chevron-left" class="h-5 w-5" />
			</button>
			<div class="min-w-0 flex-1">
				<div class="text-sm text-gray-500">{{ date(line.date) }}<template v-if="line.reference_number"> · Ref {{ line.reference_number }}</template></div>
				<div class="text-lg font-semibold break-words">{{ line.description || "No description" }}</div>
				<div v-if="line.party" class="text-sm text-gray-500">{{ line.party_type }}: {{ line.party }}</div>
			</div>
			<div class="text-right">
				<div class="text-xl font-semibold tabular" :class="line.direction === 'in' ? 'text-green-700' : ''">
					{{ line.direction === "in" ? "Received" : "Spent" }}
				</div>
				<div class="text-xl font-semibold tabular">{{ cur(line.amount, line.account_currency) }}</div>
				<div v-if="line.account_currency !== line.company_currency" class="text-xs text-gray-500">
					= {{ cur(line.amount * line.rate, line.company_currency) }} at {{ rateText }}
				</div>
			</div>
		</header>

		<!-- Already reconciled -->
		<section v-if="!line.unallocated_amount" class="rounded-lg border border-green-200 bg-green-50 p-4">
			<div class="font-medium text-green-900">Reconciled</div>
			<ul class="mt-1 text-sm">
				<li v-for="v in line.vouchers" :key="v.name">
					<a :href="deskUrl(v.doctype, v.name)" target="_blank" class="underline">{{ v.doctype }} {{ v.name }}</a> · {{ cur(v.amount, line.account_currency) }}
				</li>
			</ul>
			<Button class="mt-3" icon-left="rotate-ccw" label="Undo" :loading="busy" @click="undo" />
			<p class="mt-1 text-xs text-gray-500">Undo puts the line back to reconcile and cancels entries created from it.</p>
		</section>

		<template v-else>
			<!-- The one-click suggestion, Xero's green OK -->
			<section v-if="suggestion" class="flex items-center gap-3 rounded-lg border border-green-300 bg-green-50 p-3">
				<FeatherIcon :name="suggestion.icon" class="h-5 w-5 shrink-0 text-green-700" />
				<div class="min-w-0 flex-1 text-sm">
					<div class="font-medium text-green-900">{{ suggestion.title }}</div>
					<div class="text-green-800">{{ suggestion.detail }}</div>
				</div>
				<Button variant="solid" label="OK" :loading="busy" @click="suggestion.run" />
			</section>

			<Chips v-model="tab" :options="tabs" />

			<!-- Match -->
			<section v-if="tab === 'match'" class="space-y-4">
				<div class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-2.5 text-sm font-semibold">Payments and journals already in the books</h3>
					<p v-if="!line.suggestions.length" class="px-4 py-4 text-sm text-gray-500">Nothing uncleared within 60 days of this line.</p>
					<label v-for="s in line.suggestions" :key="s.name" class="flex cursor-pointer items-center gap-3 border-t px-4 py-2.5 text-sm first:border-t-0 hover:bg-gray-50">
						<input type="checkbox" class="form-checkbox" :checked="chosen.has(s.name)" @change="toggle(s)" />
						<div class="min-w-0 flex-1">
							<div class="font-medium">{{ s.party || s.doctype }} <span v-if="s.exact" class="ml-1 rounded bg-green-100 px-1 text-xs text-green-800">same amount</span></div>
							<div class="text-xs text-gray-500">{{ s.doctype }} {{ s.name }} · {{ date(s.date) }}<template v-if="s.reference"> · {{ s.reference }}</template></div>
						</div>
						<span class="tabular">{{ cur(s.amount, s.currency) }}</span>
					</label>
					<footer v-if="line.suggestions.length" class="flex items-center justify-between border-t px-4 py-2.5 text-sm">
						<span :class="Math.abs(chosenTotal - line.unallocated_amount) < 0.005 ? 'text-green-700' : 'text-gray-500'">
							Chosen {{ cur(chosenTotal, line.account_currency) }} of {{ cur(line.unallocated_amount, line.account_currency) }}
						</span>
						<Button variant="solid" label="Reconcile" :disabled="!chosen.size" :loading="busy" @click="matchChosen" />
					</footer>
				</div>
				<div class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-2.5 text-sm font-semibold">
						Open {{ line.direction === "in" ? "customer" : "supplier" }} invoices — paying one records the payment
					</h3>
					<p v-if="!line.invoices.length" class="px-4 py-4 text-sm text-gray-500">No open invoices.</p>
					<div v-for="inv in line.invoices" :key="inv.name" class="flex items-center gap-3 border-t px-4 py-2.5 text-sm first:border-t-0">
						<div class="min-w-0 flex-1">
							<div class="font-medium">{{ inv.party }} <span v-if="inv.exact" class="ml-1 rounded bg-green-100 px-1 text-xs text-green-800">same amount</span></div>
							<div class="text-xs text-gray-500">{{ inv.name }} · due {{ date(inv.due_date) }}</div>
						</div>
						<span class="tabular">{{ cur(inv.outstanding_amount, inv.currency) }}</span>
						<Button size="sm" label="Pay this" :loading="busy" @click="payInvoice(inv)" />
					</div>
				</div>
			</section>

			<!-- Create: who / what / why -->
			<section v-else-if="tab === 'create'" class="space-y-4 rounded-lg border bg-white p-4">
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<label>
						<span class="mb-1.5 block text-sm text-gray-600">Who <span class="text-gray-400">(optional)</span></span>
						<div class="flex gap-2">
							<select v-model="form.party_type" class="form-select w-32" aria-label="Party type">
								<option>Supplier</option><option>Customer</option><option>Employee</option>
							</select>
							<div class="min-w-0 flex-1"><LinkField v-model="form.party" :doctype="form.party_type" placeholder="Nobody" /></div>
						</div>
					</label>
					<label>
						<span class="mb-1.5 block text-sm text-gray-600">What (account)<span v-if="!form.party" class="text-red-500"> *</span></span>
						<LinkField v-model="form.account" doctype="Account" :disabled="!!form.party" :placeholder="form.party ? 'Their account' : 'e.g. 6510 Bank Charges'"
							:filters="{ is_group: 0, company: boot.company }" />
					</label>
					<label class="sm:col-span-2">
						<span class="mb-1.5 block text-sm text-gray-600">Why</span>
						<input v-model="form.remark" class="form-input w-full" :placeholder="line.description" />
					</label>
					<label v-if="!form.party">
						<span class="mb-1.5 block text-sm text-gray-600">VAT included</span>
						<LinkField v-model="form.vat" :doctype="line.direction === 'in' ? 'Sales Taxes and Charges Template' : 'Purchase Taxes and Charges Template'" placeholder="No VAT" />
					</label>
				</div>
				<p class="text-sm text-gray-500">
					<template v-if="form.party">Posts a {{ line.direction === "in" ? "receipt from" : "payment to" }} {{ form.party }}, on account — allocate it to their invoices later in desk.</template>
					<template v-else>Posts a bank entry: {{ cur(line.amount, line.account_currency) }} {{ line.direction === "in" ? "from" : "to" }} {{ form.account || "the account" }}<template v-if="form.vat">, VAT split out</template>.</template>
					<template v-if="line.account_currency !== line.company_currency"> Valued at {{ rateText }}.</template>
				</p>
				<div class="flex flex-wrap items-center justify-between gap-2">
					<router-link :to="{ path: '/bank/rules', query: { from: line.name, account: form.account || undefined } }" class="text-sm text-blue-700 hover:underline">
						Make a rule for lines like this →
					</router-link>
					<Button variant="solid" label="Create and reconcile" :disabled="!form.party && !form.account" :loading="busy" @click="create" />
				</div>
			</section>

			<!-- Transfer -->
			<section v-else-if="tab === 'transfer'" class="space-y-4 rounded-lg border bg-white p-4">
				<label class="block">
					<span class="mb-1.5 block text-sm text-gray-600">{{ line.direction === "out" ? "Moved to" : "Moved from" }}</span>
					<select v-model="xfer.bank" class="form-select w-full">
						<option value="" disabled>Pick one of our accounts</option>
						<option v-for="b in otherBanks" :key="b.name" :value="b.name">{{ b.account_name || b.name }} ({{ b.currency }})</option>
					</select>
				</label>
				<div v-if="xfer.bank && candidates.length">
					<div class="mb-1.5 text-sm text-gray-600">The other side on that account's statement</div>
					<label v-for="c in candidates" :key="c.name" class="flex cursor-pointer items-center gap-3 rounded border px-3 py-2 text-sm hover:bg-gray-50"
						:class="xfer.line === c.name ? 'border-gray-900' : ''">
						<input v-model="xfer.line" type="radio" class="form-radio" :value="c.name" />
						<span class="w-16 text-gray-500">{{ date(c.date) }}</span>
						<span class="min-w-0 flex-1 truncate">{{ c.description }}</span>
						<span class="tabular">{{ cur(c.amount, c.currency) }}</span>
					</label>
					<button v-if="xfer.line" class="mt-1 text-xs text-gray-500 underline" @click="xfer.line = ''">Not listed yet — reconcile only this side</button>
				</div>
				<label v-if="crossCurrency && !xfer.line" class="block">
					<span class="mb-1.5 block text-sm text-gray-600">Amount {{ line.direction === "out" ? "received" : "sent" }} ({{ otherBank?.currency }})</span>
					<input v-model.number="xfer.amount" type="number" step="0.01" class="form-input w-full text-right tabular" />
				</label>
				<div class="flex justify-end">
					<Button variant="solid" label="Record transfer" :disabled="!xfer.bank" :loading="busy" @click="transfer" />
				</div>
			</section>

			<!-- Discuss -->
			<section v-else class="space-y-3 rounded-lg border bg-white p-4">
				<p v-if="!line.comments.length" class="text-sm text-gray-500">Not sure what this is? Ask here — the line stays in the list until someone deals with it.</p>
				<div v-for="c in line.comments" :key="c.name" class="rounded bg-gray-50 px-3 py-2 text-sm">
					<div class="text-xs text-gray-500">{{ c.by }} · {{ relative(c.creation) }}</div>
					<div class="whitespace-pre-line" v-html="c.content" />
				</div>
				<textarea v-model="note.text" rows="2" class="form-textarea w-full" placeholder="e.g. Is this the Econet invoice?" />
				<div class="flex flex-wrap items-end gap-2">
					<label class="min-w-0 flex-1">
						<span class="mb-1.5 block text-sm text-gray-600">Ask someone <span class="text-gray-400">(optional)</span></span>
						<LinkField v-model="note.assign" doctype="User" :filters="{ user_type: 'System User', enabled: 1 }" placeholder="Nobody" />
					</label>
					<Button variant="solid" label="Post" :disabled="!note.text.trim()" :loading="busy" @click="discuss" />
				</div>
			</section>
		</template>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import { date, relative } from "@/utils/format"
import { acc, cur, ok, fail, deskUrl } from "../api"
import Chips from "@/hr/components/Chips.vue"

const props = defineProps({ name: String, banks: Array })
const emit = defineEmits(["close", "done"])

const line = ref(null)
const busy = ref(false)
const tab = ref("match")
const chosen = ref(new Map())
const form = reactive({ party_type: "Supplier", party: "", account: "", remark: "", vat: "" })
const xfer = reactive({ bank: "", line: "", amount: 0 })
const note = reactive({ text: "", assign: "" })

const rateText = computed(() => {
	const r = line.value?.rate || 0
	return r >= 1 ? `1 ${line.value.account_currency} = ${r.toFixed(4)} ${line.value.company_currency}`
		: `1 ${line.value.company_currency} = ${(1 / r).toFixed(4)} ${line.value.account_currency}`
})
const tabs = computed(() => [
	{ value: "match", label: "Match", count: (line.value?.suggestions.length || 0) + (line.value?.invoices.filter((i) => i.exact).length || 0) },
	{ value: "create", label: "Create" },
	{ value: "transfer", label: "Transfer", count: line.value?.transfer_candidates.length },
	{ value: "discuss", label: "Discuss", count: line.value?.comments.length },
])
const chosenTotal = computed(() => [...chosen.value.values()].reduce((s, v) => s + v.amount, 0))
const otherBanks = computed(() => props.banks.filter((b) => b.name !== line.value?.bank_account))
const otherBank = computed(() => props.banks.find((b) => b.name === xfer.bank))
const crossCurrency = computed(() => otherBank.value && otherBank.value.currency !== line.value.account_currency)
const candidates = computed(() => (line.value?.transfer_candidates || []).filter((c) => c.bank_account === xfer.bank))

// What one OK would do: the rule, else an exact match, else an invoice of the same amount
const suggestion = computed(() => {
	const l = line.value
	if (!l) return null
	if (l.rule && l.rule.classify_as !== "Transfer") {
		return { icon: "zap", title: `Rule: ${l.rule.rule_name}`, run: applyRule,
			detail: l.rule.classify_as === "Payment Entry" ? `Payment ${l.direction === "in" ? "from" : "to"} ${l.rule.party}` : `Post to ${l.rule.account}` }
	}
	const exact = l.suggestions.find((s) => s.exact && s.rank >= 2)
	if (exact) {
		return { icon: "link", title: `Matches ${exact.doctype} ${exact.name}`, detail: `${exact.party || ""} · ${cur(exact.amount, exact.currency)}`,
			run: () => match([exact]) }
	}
	const inv = l.invoices.find((i) => i.exact && (i.party_match || l.invoices.filter((x) => x.exact).length === 1))
	if (inv) {
		return { icon: "file-text", title: `Pays ${inv.name}`, detail: `${inv.party} · ${cur(inv.outstanding_amount, inv.currency)}`, run: () => payInvoice(inv) }
	}
	return null
})

async function load() {
	try {
		line.value = await acc("get_line", { name: props.name })
		form.remark = ""
		if (line.value.party) {
			form.party_type = line.value.party_type
			form.party = line.value.party
		} else {
			form.party_type = line.value.direction === "in" ? "Customer" : "Supplier"
		}
		if (line.value.rule?.account) form.account = line.value.rule.account
		if (!line.value.suggestions.length && !line.value.invoices.some((i) => i.exact)) {
			tab.value = line.value.transfer_candidates.some((c) => c.exact) ? "transfer" : "create"
		}
		if (line.value.transfer_candidates.length) xfer.bank = line.value.transfer_candidates[0].bank_account
	} catch (e) {
		fail(e, "Could not open the line")
	}
}

function toggle(s) {
	const m = new Map(chosen.value)
	m.has(s.name) ? m.delete(s.name) : m.set(s.name, s)
	chosen.value = m
}

async function act(fn, done) {
	busy.value = true
	try {
		const out = await fn()
		ok(done(out))
		emit("done", props.name)
	} catch (e) {
		fail(e)
	} finally {
		busy.value = false
	}
}

const match = (list) => act(() => acc("match", { name: props.name, vouchers: list.map((s) => ({ doctype: s.doctype, name: s.name, amount: s.amount })) }),
	() => "Reconciled")
const matchChosen = () => match([...chosen.value.values()])
const payInvoice = (inv) => act(() => acc("pay_invoice", { name: props.name, doctype: inv.doctype, invoice: inv.name }),
	(o) => `Paid ${inv.name} — ${o.payment_entry}`)
const applyRule = () => act(async () => {
	const out = await acc("apply_rule", { names: [props.name] })
	if (out.failed.length) throw { messages: [out.failed[0].error] }
	return out
}, (o) => `Posted by rule — ${o.done[0].voucher}`)
const create = () => act(() => acc("create", {
	name: props.name, account: form.party ? undefined : form.account, party_type: form.party ? form.party_type : undefined,
	party: form.party || undefined, remark: form.remark || undefined, vat_template: (!form.party && form.vat) || undefined,
}), (o) => `Created ${o.voucher}`)
const transfer = () => act(() => acc("transfer", {
	name: props.name, other_bank_account: xfer.bank, other_line: xfer.line || undefined,
	other_amount: crossCurrency.value && !xfer.line ? xfer.amount : undefined,
}), (o) => `Transfer recorded — ${o.payment_entry}`)

async function undo() {
	busy.value = true
	try {
		await acc("unreconcile", { name: props.name })
		ok("Back to reconcile")
		emit("done", props.name)
	} catch (e) {
		fail(e)
	} finally {
		busy.value = false
	}
}

async function discuss() {
	busy.value = true
	try {
		line.value.comments = await acc("discuss", { name: props.name, text: note.text, assign_to: note.assign || undefined })
		ok(note.assign ? "Asked" : "Posted", note.assign ? `${note.assign} will see it on their Home` : undefined)
		note.text = ""
		note.assign = ""
	} catch (e) {
		fail(e)
	} finally {
		busy.value = false
	}
}

watch(() => xfer.bank, () => {
	xfer.line = candidates.value.length === 1 ? candidates.value[0].name : ""
	if (crossCurrency.value && line.value) {
		// prefilled at the day's rate; change it to what the other statement actually shows
		xfer.amount = Number((line.value.amount * (line.value.rates?.[otherBank.value.currency] || 0)).toFixed(2))
	}
})

// Enter accepts the suggestion
function onKey(e) {
	if (e.key !== "Enter" || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(e.target.tagName)) return
	if (suggestion.value && !busy.value) suggestion.value.run()
}
onMounted(() => window.addEventListener("keydown", onKey))
onBeforeUnmount(() => window.removeEventListener("keydown", onKey))

load()
</script>
