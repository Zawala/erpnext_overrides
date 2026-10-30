<template>
	<Dialog :model-value="open" :options="{ title: isNew ? 'New salary component' : component.name, size: 'xl' }"
		@update:model-value="(v) => !v && $emit('close')">
		<template #body-content>
			<div class="space-y-4">
				<p v-if="error" class="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
				<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Name <span class="text-red-500">*</span></span>
					<input v-model.trim="doc.name" :disabled="!isNew" class="form-input w-full" placeholder="e.g. Transport Allowance" />
					<span v-if="!isNew" class="mt-1 block text-xs text-gray-500">The name can't change: payslips and structures refer to it.</span></label>

				<div v-if="isNew" class="flex flex-wrap gap-1" role="radiogroup" aria-label="What it is">
					<button v-for="k in KINDS" :key="k.value" role="radio" :aria-checked="kind === k.value"
						class="rounded-full border px-3 py-1 text-sm" :class="kind === k.value ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-700'"
						@click="kind = k.value">{{ k.label }}</button>
				</div>
				<p class="text-xs text-gray-500">{{ KINDS.find((k) => k.value === kind).hint }}</p>

				<label class="block max-w-xs"><span class="mb-1.5 block text-sm text-gray-600">Short code <span class="text-red-500">*</span></span>
					<input v-model.trim="doc.abbr" class="form-input w-full font-mono" placeholder="e.g. TA" @input="touched = true" />
					<span class="mt-1 block text-xs text-gray-500">How formulas refer to it. Letters, digits and _.</span></label>
				<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Description</span>
					<input v-model="doc.description" class="form-input w-full" placeholder="Shown to HR only" /></label>

				<div class="space-y-1.5 rounded border p-3 text-sm">
					<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Usual settings (each structure line can differ)</p>
					<label v-if="kind === 'earning'" class="flex items-center gap-2"><input v-model="doc.is_tax_applicable" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" /> Taxable</label>
					<label v-if="kind === 'deduction'" class="flex items-center gap-2"><input v-model="doc.exempted_from_income_tax" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" /> Comes off before tax (like a pension)</label>
					<label class="flex items-center gap-2"><input v-model="doc.depends_on_payment_days" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" /> Reduced for unpaid days</label>
					<label v-if="!isNew" class="flex items-center gap-2"><input v-model="doc.disabled" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" /> Disabled — not offered for new structures</label>
				</div>
				<p v-if="component?.used_in?.length" class="text-xs text-gray-500">On {{ component.used_in.join(", ") }}.</p>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button label="Cancel" @click="$emit('close')" />
				<Button variant="solid" :label="isNew ? 'Create' : 'Save'" :loading="saving" :disabled="!doc.name || !doc.abbr" @click="save" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { Dialog } from "frappe-ui"
import { pay, ok, errorMessages } from "../api"

const props = defineProps({ open: Boolean, component: Object, presetKind: String })
const emit = defineEmits(["close", "saved"])

const KINDS = [
	{ value: "earning", label: "Earning", hint: "Adds to gross pay — basic, allowances, commission." },
	{ value: "deduction", label: "Deduction", hint: "Comes out of pay — pension, PAYE, loans." },
	{ value: "employer", label: "Employer cost", hint: "Shown on the payslip, paid by the company, not taken from pay — e.g. a levy." },
]
const isNew = computed(() => !props.component)
const kind = ref("earning")
const doc = reactive({})
const error = ref("")
const saving = ref(false)
const touched = ref(false)

watch(() => props.open, (open) => {
	if (!open) return
	const c = props.component
	error.value = ""
	touched.value = !!c
	kind.value = c ? (c.type === "Earning" ? "earning" : c.do_not_include_in_total ? "employer" : "deduction") : props.presetKind || "earning"
	Object.assign(doc, {
		name: c?.name || "", abbr: c?.abbr || "", description: c?.description || "", disabled: c?.disabled || 0,
		is_tax_applicable: c ? c.is_tax_applicable : 1, exempted_from_income_tax: c?.exempted_from_income_tax || 0,
		depends_on_payment_days: c ? c.depends_on_payment_days : 1,
	})
}, { immediate: true })

// suggest a short code from the name until one is typed
watch(() => doc.name, (n) => {
	if (!touched.value && isNew.value) doc.abbr = (n || "").split(/\s+/).filter(Boolean).map((w) => w[0]).join("").toUpperCase().replace(/[^A-Z0-9_]/g, "")
})

async function save() {
	saving.value = true
	error.value = ""
	try {
		const setup = await pay("save_component", { component: { ...doc, type: kind.value === "earning" ? "Earning" : "Deduction", employer: kind.value === "employer" ? 1 : 0 } })
		ok(isNew.value ? `Created ${doc.name}` : `Saved ${doc.name}`)
		emit("saved", setup, doc.name, kind.value)
	} catch (e) {
		error.value = errorMessages(e).join(" ")
	} finally {
		saving.value = false
	}
}
</script>
