<template>
	<div class="space-y-5">
		<section v-for="g in GROUPS" :key="g.kind">
			<div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<div>
					<h3 class="font-semibold">{{ g.label }}</h3>
					<p class="text-xs text-gray-500">{{ g.hint }}</p>
				</div>
				<div v-if="editable" class="flex flex-wrap gap-1">
					<Button size="sm" variant="ghost" icon-left="plus" :label="g.add" :disabled="!free(g.kind).length" @click="add(g.kind)" />
					<Button size="sm" variant="ghost" icon-left="file-plus" label="New component" @click="$emit('new-component', g.kind)" />
				</div>
			</div>
			<p v-if="!of(g.kind).length" class="rounded border border-dashed px-3 py-3 text-sm text-gray-400">{{ g.empty }}</p>
			<ol class="space-y-2">
				<li v-for="(r, i) in of(g.kind)" :key="r._key" class="rounded-lg border bg-white p-3">
					<div class="flex flex-wrap items-center gap-2">
						<select v-model="r.component" :disabled="!editable" class="form-select min-w-0 flex-1 font-medium" :aria-label="`${g.label} line ${i + 1}`"
							@change="pickComponent(r)">
							<option v-for="c in choices(r)" :key="c.name" :value="c.name">{{ c.name }}{{ c.disabled ? " (disabled)" : "" }}</option>
						</select>
						<span class="hidden text-xs text-gray-400 sm:inline" title="Short code, for formulas">{{ abbrOf(r.component) }}</span>
						<div v-if="editable" class="flex">
							<button class="rounded p-1.5 text-gray-500 hover:bg-gray-100 disabled:opacity-30" :disabled="i === 0" aria-label="Move up" @click="move(r, -1)">
								<FeatherIcon name="arrow-up" class="h-4 w-4" /></button>
							<button class="rounded p-1.5 text-gray-500 hover:bg-gray-100 disabled:opacity-30" :disabled="i === of(g.kind).length - 1" aria-label="Move down" @click="move(r, 1)">
								<FeatherIcon name="arrow-down" class="h-4 w-4" /></button>
							<button class="rounded p-1.5 text-gray-500 hover:bg-red-50 hover:text-red-600" :aria-label="`Remove ${r.component}`" @click="remove(r)">
								<FeatherIcon name="x" class="h-4 w-4" /></button>
						</div>
					</div>

					<!-- How it's worked out -->
					<div class="mt-2 flex flex-wrap gap-1" role="radiogroup" :aria-label="`How ${r.component} is worked out`">
						<button v-for="mo in methods(g.kind)" :key="mo.value" role="radio" :aria-checked="r.method === mo.value" :disabled="!editable || mo.disabled?.(r)"
							class="rounded-full border px-2.5 py-0.5 text-xs disabled:opacity-40"
							:class="r.method === mo.value ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'"
							:title="mo.disabled?.(r) ? 'Another line already comes from the tax bands' : ''"
							@click="setMethod(r, mo.value)">{{ mo.label }}</button>
					</div>

					<div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
						<template v-if="r.method === 'fixed'">
							<span class="text-gray-600">{{ currency }}</span>
							<input v-model.number="r.amount" type="number" min="0" step="0.01" :disabled="!editable" class="form-input w-28 text-right tabular" aria-label="Amount" />
							<span class="text-gray-500">a month</span>
						</template>
						<template v-else-if="r.method === 'percent' || r.method === 'capped'">
							<input v-model.number="r.rate" type="number" min="0" step="0.1" :disabled="!editable" class="form-input w-20 text-right tabular" aria-label="Percent" />
							<span class="text-gray-600">% of</span>
							<select v-if="g.kind !== 'earning'" v-model="r.of" :disabled="!editable" class="form-select w-auto">
								<option value="base">the base salary</option><option value="gross_pay">gross pay</option>
							</select>
							<span v-else class="text-gray-600">the base salary</span>
							<template v-if="r.method === 'capped'">
								<span class="text-gray-600">, at most {{ currency }}</span>
								<input v-model.number="r.cap" type="number" min="0" step="0.01" :disabled="!editable" class="form-input w-24 text-right tabular" aria-label="Most it can be" />
							</template>
						</template>
						<span v-else-if="r.method === 'tax'" class="text-gray-600">PAYE from the tax bands picked for each person, on taxable pay.</span>
						<div v-else class="w-full">
							<input v-model.trim="r.formula" :disabled="!editable" class="form-input w-full font-mono text-sm" placeholder="e.g. base * 0.05 + 10" aria-label="Formula" />
							<p class="mt-1 text-xs text-gray-500">Can use: <code>base</code>{{ g.kind !== 'earning' ? ", gross_pay" : "" }}, payment_days, total_working_days<template v-if="above(r).length">,
								and the lines above: <code v-for="(a, j) in above(r)" :key="a">{{ a }}{{ j < above(r).length - 1 ? ", " : "" }}</code></template>.</p>
						</div>
					</div>
					<p class="mt-1.5 text-xs text-gray-500">{{ sentence(r) }}</p>

					<!-- Plain-language flags -->
					<div v-if="r.method !== 'tax'" class="mt-2 flex flex-wrap gap-x-5 gap-y-1 border-t pt-2 text-sm">
						<label v-if="g.kind === 'earning'" class="flex items-center gap-1.5"><input v-model="r.is_tax_applicable" type="checkbox" :true-value="1" :false-value="0" :disabled="!editable" class="form-checkbox" /> Taxable</label>
						<label v-if="g.kind === 'deduction'" class="flex items-center gap-1.5"><input v-model="r.exempted_from_income_tax" type="checkbox" :true-value="1" :false-value="0" :disabled="!editable" class="form-checkbox" /> Comes off before tax</label>
						<label class="flex items-center gap-1.5" title="Unpaid leave and part months reduce it"><input v-model="r.depends_on_payment_days" type="checkbox" :true-value="1" :false-value="0" :disabled="!editable" class="form-checkbox" /> Reduced for unpaid days</label>
					</div>
				</li>
			</ol>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { money } from "@/utils/format"

const props = defineProps({ rows: Array, components: Array, editable: Boolean, currency: String })
defineEmits(["new-component"])

const GROUPS = [
	{ kind: "earning", label: "Earnings", add: "Add earning", hint: "Worked out first; they add up to gross pay.", empty: "No earnings — add Basic." },
	{ kind: "deduction", label: "Deductions", add: "Add deduction", hint: "Taken from gross pay to give take-home pay.", empty: "No deductions." },
	{ kind: "employer", label: "Employer costs", add: "Add employer cost", hint: "On the payslip for information; not taken from pay (e.g. a levy).", empty: "None." },
]
const METHODS = [
	{ value: "fixed", label: "Fixed amount" },
	{ value: "percent", label: "% of salary" },
	{ value: "capped", label: "% with a cap" },
	{ value: "tax", label: "From the tax bands", kinds: ["deduction"], disabled: (r) => props.rows.some((x) => x !== r && x.method === "tax") },
	{ value: "formula", label: "Advanced formula" },
]
const methods = (kind) => METHODS.filter((m) => !m.kinds || m.kinds.includes(kind))

let next = 0
for (const r of props.rows) r._key ??= ++next
const of = (kind) => props.rows.filter((r) => r.kind === kind)
const typeOf = (kind) => (kind === "earning" ? "Earning" : "Deduction")
const byName = computed(() => Object.fromEntries((props.components || []).map((c) => [c.name, c])))
const abbrOf = (name) => byName.value[name]?.abbr || ""
const used = computed(() => new Set(props.rows.map((r) => r.component)))
const free = (kind) => (props.components || []).filter((c) => c.type === typeOf(kind) && !c.disabled && !used.value.has(c.name))
const choices = (r) => (props.components || []).filter((c) => c.type === typeOf(r.kind) && (c.name === r.component || (!c.disabled && !used.value.has(c.name))))
// abbreviations a formula may use: every earning, and deductions above this one
function above(r) {
	const order = [...of("earning"), ...props.rows.filter((x) => x.kind !== "earning")]
	return order.slice(0, order.indexOf(r)).map((x) => abbrOf(x.component)).filter(Boolean)
}

function defaults(c, kind) {
	return {
		depends_on_payment_days: c?.depends_on_payment_days ?? 1,
		is_tax_applicable: kind === "earning" ? (c?.is_tax_applicable ?? 1) : 0,
		exempted_from_income_tax: kind === "deduction" ? (c?.exempted_from_income_tax ?? 0) : 0,
	}
}
function add(kind, name) {
	const c = name ? byName.value[name] : free(kind)[0]
	if (!c) return
	const tax = kind === "deduction" && c.variable_based_on_taxable_salary && !props.rows.some((x) => x.method === "tax")
	props.rows.push({ _key: ++next, kind, component: c.name, method: tax ? "tax" : "fixed", of: "base", amount: null, rate: null,
		cap: null, formula: "", ...defaults(c, kind) })
}
function pickComponent(r) {
	Object.assign(r, defaults(byName.value[r.component], r.kind))
}
function remove(r) {
	props.rows.splice(props.rows.indexOf(r), 1)
}
function move(r, step) {
	const same = of(r.kind)
	const other = same[same.indexOf(r) + step]
	if (!other) return
	const a = props.rows.indexOf(r), b = props.rows.indexOf(other)
	props.rows.splice(a, 1, other)
	props.rows.splice(b, 1, r)
}
function setMethod(r, method) {
	if (method === "percent" && !r.rate) r.rate = r.kind === "earning" && !of("earning").some((x) => x !== r) ? 100 : null
	r.method = method
}

const m = (v) => money(v || 0, props.currency)
function sentence(r) {
	const what = r.of === "gross_pay" ? "gross pay" : "the base salary"
	const unpaid = r.depends_on_payment_days ? " Less for unpaid days." : ""
	switch (r.method) {
		case "fixed": return r.amount ? `${m(r.amount)} every month.${unpaid}` : "Enter the amount."
		case "percent": return r.rate ? `${r.rate}% of ${what}.${unpaid}` : "Enter the percentage."
		case "capped": return r.rate && r.cap ? `${r.rate}% of ${what}, but never more than ${m(r.cap)}.${unpaid}` : "Enter the percentage and the most it can be."
		case "tax": return "Worked out from each person's taxable pay and their tax bands."
		default: return r.formula ? `Formula: ${r.formula}` : "Enter a formula."
	}
}
</script>
