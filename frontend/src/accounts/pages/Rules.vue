<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Bank rules" subtitle="Lines that come every month are coded once, then OK'd in bulk" back="/bank">
			<Button icon-left="refresh-cw" label="Run rules" :loading="running" @click="runRules" />
			<Button variant="solid" icon-left="plus" label="New rule" @click="edit(null)" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1400px] p-4 lg:p-6 space-y-4">
			<p class="text-sm text-gray-500">
				Each line still to reconcile gets the first rule (lowest priority number) whose conditions it meets. On Bank, a rule
				match shows <FeatherIcon name="zap" class="inline h-3.5 w-3.5 text-blue-700" /> and one <b>OK</b> posts it.
			</p>
			<div v-if="!rules" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<Empty v-else-if="!rules.length" icon="zap">No rules yet. Start with bank charges and the 2% transfer tax — they're a third of every statement.</Empty>
			<div v-else class="overflow-x-auto rounded-lg border bg-white">
				<table class="w-full text-sm">
					<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
						<tr>
							<th class="px-4 py-2 font-medium">#</th>
							<th class="px-2 py-2 font-medium">Rule</th>
							<th class="px-2 py-2 font-medium">When the description</th>
							<th class="px-2 py-2 font-medium">Lines</th>
							<th class="px-2 py-2 font-medium">Posts to</th>
							<th class="px-4 py-2 text-right font-medium">Waiting</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="r in rules" :key="r.name" class="cursor-pointer border-t align-top hover:bg-gray-50" @click="edit(r)">
							<td class="px-4 py-2 tabular text-gray-500">{{ r.priority }}</td>
							<td class="px-2 py-2 font-medium">{{ r.rule_name }}</td>
							<td class="px-2 py-2 text-gray-600">
								<div v-for="c in r.conditions" :key="c.value"><span class="text-gray-400">{{ c.check.toLowerCase() }}</span> {{ c.value }}</div>
								<div v-if="r.min_amount || r.max_amount" class="text-gray-400">amount {{ r.min_amount || 0 }}–{{ r.max_amount || "any" }}</div>
							</td>
							<td class="px-2 py-2">{{ r.transaction_type === "Withdrawal" ? "Money out" : r.transaction_type === "Deposit" ? "Money in" : "Both" }}</td>
							<td class="px-2 py-2">{{ r.classify_as === "Payment Entry" ? `Payment · ${r.party}` : r.classify_as === "Transfer" ? `Transfer · ${r.account}` : r.account }}</td>
							<td class="px-4 py-2 text-right tabular">
								<router-link v-if="r.hits" to="/bank" class="text-blue-700 hover:underline" @click.stop>{{ r.hits }}</router-link>
								<span v-else class="text-gray-400">0</span>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>

		<Dialog v-model="open" :options="{ title: form.name ? `Rule · ${form.rule_name}` : 'New rule', size: '2xl' }">
			<template #body-content>
				<div class="space-y-4">
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<label class="sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Name</span>
							<input v-model="form.rule_name" class="form-input w-full" :disabled="!!form.name" placeholder="e.g. Bank charges" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Priority</span>
							<input v-model.number="form.priority" type="number" min="1" class="form-input w-full" />
							<span class="mt-1 block text-xs text-gray-500">Lower runs first</span></label>
					</div>
					<div>
						<div class="mb-1.5 text-sm text-gray-600">When the description…</div>
						<div v-for="(c, i) in form.conditions" :key="i" class="mb-2 flex gap-2">
							<select v-model="c.check" class="form-select w-36" aria-label="How to compare">
								<option>Contains</option><option>Starts With</option><option>Ends With</option><option>Regex</option>
							</select>
							<input v-model="c.value" class="form-input min-w-0 flex-1" :placeholder="c.check === 'Regex' ? 'TRANSFER CHARGE|SERVICE CHARGE' : 'SERVICE CHARGE'" />
							<button class="rounded p-1.5 text-gray-500 hover:bg-gray-100" aria-label="Remove condition" @click="form.conditions.splice(i, 1)">
								<FeatherIcon name="x" class="h-4 w-4" />
							</button>
						</div>
						<button class="text-sm text-blue-700 hover:underline" @click="form.conditions.push({ check: 'Contains', value: '' })">+ or another</button>
						<p class="mt-1 text-xs text-gray-500">Any one condition is enough. Upper or lower case doesn't matter.</p>
					</div>
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">Lines</span>
							<select v-model="form.transaction_type" class="form-select w-full">
								<option value="Withdrawal">Money out</option><option value="Deposit">Money in</option><option value="Any">Both</option>
							</select></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Amount from</span>
							<input v-model.number="form.min_amount" type="number" min="0" class="form-input w-full" placeholder="any" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Amount to</span>
							<input v-model.number="form.max_amount" type="number" min="0" class="form-input w-full" placeholder="any" /></label>
					</div>
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">Post as</span>
							<select v-model="form.classify_as" class="form-select w-full">
								<option value="Bank Entry">To an account</option><option value="Payment Entry">Payment to/from a party</option>
							</select></label>
						<label v-if="form.classify_as === 'Payment Entry'" class="sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Party</span>
							<div class="flex gap-2">
								<select v-model="form.party_type" class="form-select w-32" aria-label="Party type"><option>Supplier</option><option>Customer</option><option>Employee</option></select>
								<div class="min-w-0 flex-1"><LinkField v-model="form.party" :doctype="form.party_type" /></div>
							</div></label>
						<label v-else class="sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Account</span>
							<LinkField v-model="form.account" doctype="Account" :filters="{ is_group: 0, company: boot.company }" placeholder="e.g. 6510 Bank Charges" /></label>
					</div>
					<div class="rounded bg-gray-50 px-3 py-2 text-sm">
						<span v-if="previewing" class="text-gray-500">Checking…</span>
						<template v-else-if="preview">
							Would catch <b>{{ preview.count }}</b> line{{ preview.count === 1 ? "" : "s" }} still to reconcile.
							<div v-for="s in preview.sample" :key="s.name" class="truncate text-xs text-gray-500">
								{{ s.date }} · {{ s.description }} · {{ (s.withdrawal || s.deposit).toFixed(2) }}
							</div>
						</template>
						<span v-else class="text-gray-500">Add a condition to see what it would catch.</span>
					</div>
					<p v-if="error" class="text-sm text-red-700">{{ error }}</p>
				</div>
			</template>
			<template #actions>
				<div class="flex gap-2">
					<Button v-if="form.name" theme="red" label="Delete" :loading="saving" @click="remove" />
					<Button class="flex-1" variant="solid" label="Save rule" :loading="saving" @click="save" />
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { Dialog, LoadingIndicator, debounce } from "frappe-ui"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import { acc, ok, fail, errorMessages } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"
import Empty from "@/hr/components/Empty.vue"

const route = useRoute()
const rules = ref(null)
const open = ref(false)
const saving = ref(false)
const running = ref(false)
const error = ref("")
const preview = ref(null)
const previewing = ref(false)
const BLANK = () => ({ name: "", rule_name: "", priority: 10, transaction_type: "Withdrawal", min_amount: null, max_amount: null,
	classify_as: "Bank Entry", account: "", party_type: "Supplier", party: "", conditions: [{ check: "Contains", value: "" }] })
const form = reactive(BLANK())

async function load() {
	try {
		rules.value = await acc("get_rules")
	} catch (e) {
		fail(e, "Could not load the rules")
	}
}

function edit(r) {
	Object.assign(form, BLANK(), r ? JSON.parse(JSON.stringify(r)) : {})
	if (!form.conditions.length) form.conditions.push({ check: "Contains", value: "" })
	error.value = ""
	preview.value = null
	open.value = true
}

// Opened from a statement line ("Make a rule for lines like this"): its description, minus numbers and references
async function fromLine(name) {
	const l = await acc("get_line", { name })
	const words = (l.description || "").toUpperCase().replace(/REF:.*$|SEQ:.*$|\d{4,}/g, " ").replace(/[|]/g, " ").replace(/\s+/g, " ").trim()
	edit(null)
	Object.assign(form, {
		rule_name: words.split(" ").slice(0, 4).join(" ").toLowerCase().replace(/^./, (c) => c.toUpperCase()),
		transaction_type: l.direction === "in" ? "Deposit" : "Withdrawal",
		account: route.query.account || "", conditions: [{ check: "Contains", value: words.split(" ").slice(0, 4).join(" ") }],
	})
}

const runPreview = debounce(async () => {
	if (!open.value || !form.conditions.some((c) => c.value?.trim())) return (preview.value = null)
	previewing.value = true
	try {
		preview.value = await acc("preview_rule", { rule: { ...form } })
	} catch {
		preview.value = null
	} finally {
		previewing.value = false
	}
}, 400)
watch(() => [form.conditions.map((c) => c.check + c.value).join(), form.transaction_type, form.min_amount, form.max_amount, open.value], runPreview)

async function save() {
	saving.value = true
	error.value = ""
	try {
		await acc("save_rule", { rule: { ...form, conditions: form.conditions.filter((c) => c.value?.trim()) } })
		ok("Rule saved", "Lines it catches now show on Bank with OK")
		open.value = false
		await load()
	} catch (e) {
		error.value = errorMessages(e).join(" ")
	} finally {
		saving.value = false
	}
}

async function remove() {
	saving.value = true
	try {
		rules.value = await acc("delete_rule", { name: form.name })
		open.value = false
		ok("Rule deleted")
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

async function runRules() {
	running.value = true
	try {
		const n = await acc("run_rules")
		ok("Rules run", `${n} line${n === 1 ? "" : "s"} matched a rule`)
		await load()
	} catch (e) {
		fail(e)
	} finally {
		running.value = false
	}
}

load()
if (route.query.from) fromLine(route.query.from).catch((e) => fail(e))
</script>
