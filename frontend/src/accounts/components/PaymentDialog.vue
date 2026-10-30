<template>
	<Dialog v-model="open" :options="{ title: 'Make a payment', size: 'lg' }">
		<template #body-content>
			<div class="space-y-4">
				<!-- To whom -->
				<div class="inline-flex rounded-md border p-0.5 text-sm">
					<button v-for="k in KINDS" :key="k.value" class="rounded px-3 py-1.5"
						:class="form.kind === k.value ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-100'"
						@click="form.kind = k.value">{{ k.label }}</button>
				</div>

				<template v-if="form.kind === 'supplier'">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Supplier <span class="text-red-500">*</span></span>
						<LinkField v-model="form.supplier" doctype="Supplier" /></label>
					<div v-if="form.supplier">
						<div class="mb-1.5 text-sm text-gray-600">Bills this pays</div>
						<div v-if="bills === null" class="py-2"><LoadingIndicator class="h-4 w-4 text-gray-500" /></div>
						<p v-else-if="!bills.length" class="text-sm text-gray-500">No open bills — the payment goes on account, to set against their next bill.</p>
						<div v-else class="max-h-48 divide-y overflow-y-auto rounded border">
							<label v-for="b in bills" :key="b.name" class="flex items-center gap-3 px-3 py-2 text-sm"
								:class="b.match && !b.match.payable ? 'cursor-not-allowed bg-gray-50/70' : 'cursor-pointer hover:bg-gray-50'"
								:title="b.match && !b.match.payable ? `Can't pay yet: ${b.match.message}` : ''">
								<input v-model="form.invoices" type="checkbox" :value="b.name" class="rounded" :disabled="b.match && !b.match.payable" />
								<span class="min-w-0 flex-1 truncate"><b class="font-medium">{{ b.name }}</b>
									<span class="text-gray-500"><template v-if="b.bill_no"> · {{ b.bill_no }}</template> · due {{ date(b.due_date) }}</span>
									<span v-if="b.match && !b.match.payable" class="block truncate text-xs text-amber-800">{{ b.match.label }}: {{ b.match.message }}</span></span>
								<span v-if="b.match" class="rounded px-1.5 py-0.5 text-xs" :class="MATCH_THEME[b.match.status]">{{ b.match.label }}</span>
								<span class="tabular">{{ cur(b.outstanding_amount, b.currency) }}</span>
							</label>
						</div>
					</div>
				</template>

				<template v-else>
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Paid to (account) <span class="text-red-500">*</span></span>
							<LinkField v-model="form.account" doctype="Account" :filters="accountFilters" placeholder="e.g. Bank Charges, PAYE" /></label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">VAT included</span>
							<LinkField v-model="form.vat" doctype="Purchase Taxes and Charges Template" placeholder="No VAT" /></label>
					</div>
				</template>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">From</span>
						<select v-model="form.bank" class="form-select w-full">
							<option v-for="b in boot.banks" :key="b.name" :value="b.name">{{ b.account_name || b.name }} ({{ b.currency }})</option>
						</select></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Date</span><input v-model="form.date" type="date" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Amount ({{ bankCurrency }}) <span class="text-red-500">*</span></span>
						<input v-model.number="form.amount" type="number" step="0.01" min="0" class="form-input w-full text-right tabular" @input="amountTouched = true" /></label>
				</div>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Reference</span>
						<input v-model="form.reference" class="form-input w-full" placeholder="Bank reference or cheque number" /></label>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">What for</span>
						<input v-model="form.remark" class="form-input w-full" placeholder="e.g. Courier, October rent" /></label>
				</div>

				<p v-if="note" class="text-xs text-amber-700">{{ note }}</p>
				<p class="text-xs text-gray-500">Posted straight away. When it shows on the bank statement, Bank suggests this payment as the match.</p>
			</div>
		</template>
		<template #actions>
			<Button class="w-full" variant="solid" :label="ready ? `Pay ${cur(form.amount, bankCurrency)}` : 'Pay'" :disabled="!ready" :loading="saving" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { Dialog, LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import { date, today } from "@/utils/format"
import { acc, cur, ok, fail } from "../api"
import { MATCH_THEME } from "../records"

const open = defineModel({ type: Boolean, default: false })
// `bill` preselects a supplier bill (from a Pay button): { name, supplier, currency }
const props = defineProps({ bill: { type: Object, default: null } })
const emit = defineEmits(["paid"])

const KINDS = [{ value: "supplier", label: "A supplier" }, { value: "account", label: "An expense or other account" }]
const accountFilters = { is_group: 0, company: boot.company, account_type: ["not in", ["Bank", "Cash", "Receivable", "Payable"]] }
const form = reactive({})
const bills = ref(null)
const saving = ref(false)
const amountTouched = ref(false)

const bank = computed(() => boot.banks?.find((b) => b.name === form.bank))
const bankCurrency = computed(() => bank.value?.currency || boot.currency)
const ticked = computed(() => (bills.value || []).filter((b) => form.invoices.includes(b.name)))
const ready = computed(() => form.bank && Number(form.amount) > 0 && (form.kind === "supplier" ? form.supplier : form.account))
const note = computed(() => {
	const other = ticked.value.find((b) => b.currency !== bankCurrency.value)
	return other ? `The bill is in ${other.currency}; the ${bankCurrency.value} amount is converted at the day's rate.` : ""
})

function bankFor(currency) {
	return boot.banks?.find((b) => b.currency === currency)?.name || boot.banks?.[0]?.name
}

function reset() {
	Object.assign(form, { kind: "supplier", supplier: props.bill?.supplier || "", invoices: props.bill ? [props.bill.name] : [],
		account: "", vat: "", bank: bankFor(props.bill?.currency || boot.currency), date: today(), amount: null, reference: "", remark: "" })
	amountTouched.value = false
}

watch(open, (v) => v && reset(), { immediate: true })

watch(() => form.supplier, async (s) => {
	bills.value = null
	if (!s) return
	try {
		bills.value = await acc("get_open_invoices", { party_type: "Supplier", party: s })
		// a bill that isn't matched to what was ordered and received can't be paid (erp_overrides.three_way)
		const unpayable = new Set(bills.value.filter((b) => b.match && !b.match.payable).map((b) => b.name))
		form.invoices = form.invoices.filter((n) => !unpayable.has(n))
	} catch (e) {
		bills.value = []
		fail(e)
	}
})

// The amount follows the ticked bills until it is typed over
watch(ticked, (t) => {
	if (amountTouched.value || !t.length) return
	if (t[0].currency !== bankCurrency.value) form.bank = bankFor(t[0].currency) || form.bank
	if (t[0].currency === bankCurrency.value) form.amount = Number(t.reduce((s, b) => s + b.outstanding_amount, 0).toFixed(2))
})

async function save() {
	saving.value = true
	try {
		const out = await acc("make_payment", {
			bank_account: form.bank, amount: form.amount, posting_date: form.date,
			reference_no: form.reference || undefined, remark: form.remark || undefined,
			...(form.kind === "supplier"
				? { supplier: form.supplier, invoices: form.invoices }
				: { account: form.account, vat_template: form.vat || undefined }),
		})
		ok("Payment made", `${out.voucher} — track it under Payments`)
		open.value = false
		emit("paid", out)
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

</script>
