<template>
	<Dialog :model-value="open" :options="{ title: isNew ? 'New leave type' : `Leave type · ${name}`, size: '3xl' }"
		@update:model-value="(v) => !v && $emit('close')">
		<template #body-content>
			<div v-if="!doc" class="p-6 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<div v-else class="space-y-5">
				<div v-if="errors.length" class="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
					<p v-for="m in errors" :key="m">{{ m }}</p>
				</div>

				<!-- Basics -->
				<section class="grid grid-cols-1 gap-4 sm:grid-cols-3">
					<label class="sm:col-span-3"><span class="mb-1.5 block text-sm text-gray-600">Name <span class="text-red-500">*</span></span>
						<input v-model="doc.leave_type_name" class="form-input w-full" :disabled="!isNew" placeholder="e.g. Maternity Leave" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Max days a year</span>
						<input v-model.number="doc.max_leaves_allowed" type="number" min="0" step="0.5" class="form-input w-full" />
						<span class="mt-1 block text-xs text-gray-500">0 = no ceiling, not zero days</span></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Max days in a row</span>
						<input v-model.number="doc.max_continuous_days_allowed" type="number" min="0" class="form-input w-full" />
						<span class="mt-1 block text-xs text-gray-500">0 = no limit</span></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Usable after (working days employed)</span>
						<input v-model.number="doc.applicable_after" type="number" min="0" class="form-input w-full" /></label>
				</section>

				<section class="grid grid-cols-1 gap-2 sm:grid-cols-2">
					<Check v-model="doc.is_lwp" :disabled="!!doc.is_ppl" label="Unpaid (Leave Without Pay)" hint="Payroll deducts these days; no balance needed" />
					<Check v-model="doc.include_holiday" label="Count public holidays inside a request as leave" hint="Usually off — “it charged me for the holiday”" warn />
					<Check v-model="doc.allow_negative" label="Allow a negative balance" hint="Lets people go into the red" warn />
					<Check v-model="doc.is_optional_leave" label="Optional holiday leave" hint="Only usable on days in the optional holiday list" />
					<Check v-model="doc.is_compensatory" label="Compensatory off" hint="Earned by working on a holiday" />
					<Check v-model="doc.is_ppl" :disabled="!!doc.is_lwp" label="Partially paid" hint="A fraction of the daily salary is paid" />
					<label v-if="doc.is_ppl" class="sm:col-start-2"><span class="mb-1.5 block text-sm text-gray-600">Fraction of daily salary paid</span>
						<input v-model.number="doc.fraction_of_daily_salary_per_leave" type="number" min="0" max="1" step="0.05" class="form-input w-full" /></label>
				</section>

				<!-- Earned leave: the automatic monthly allocation -->
				<section class="rounded-lg border p-4 space-y-3" :class="doc.is_earned_leave ? 'border-green-200 bg-green-50/40' : ''">
					<Check v-model="doc.is_earned_leave" label="Earned leave — allocate automatically over the year"
						hint="Instead of the whole year on day one, the scheduler adds a share every period. A January leaver hasn't earned the year." />
					<div v-if="doc.is_earned_leave" class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">Every</span>
							<select v-model="doc.earned_leave_frequency" class="form-select w-full">
								<option v-for="f in ['Monthly', 'Quarterly', 'Half-Yearly', 'Yearly']" :key="f">{{ f }}</option>
							</select></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">On the</span>
							<select v-model="doc.allocate_on_day" class="form-select w-full">
								<option v-for="f in ['First Day', 'Last Day', 'Date of Joining']" :key="f">{{ f }}</option>
							</select></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Round to</span>
							<select v-model="doc.rounding" class="form-select w-full">
								<option value="">No rounding</option><option value="0.25">¼ day</option><option value="0.5">½ day</option><option value="1.0">Whole days</option>
							</select></label>
						<p class="sm:col-span-3 text-sm text-green-900">{{ earnedExample }}</p>
					</div>
				</section>

				<!-- Carry forward -->
				<section class="rounded-lg border p-4 space-y-3">
					<Check v-model="doc.is_carry_forward" label="Carry unused days into next period" hint="Cap it, or balances grow forever" />
					<div v-if="doc.is_carry_forward" class="grid grid-cols-1 gap-4 sm:grid-cols-2">
						<label><span class="mb-1.5 block text-sm text-gray-600">Most days carried</span>
							<input v-model.number="doc.maximum_carry_forwarded_leaves" type="number" min="0" step="0.5" class="form-input w-full" />
							<span class="mt-1 block text-xs" :class="Number(doc.maximum_carry_forwarded_leaves) ? 'text-gray-500' : 'text-amber-700'">0 = no cap</span></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Carried days expire after (days)</span>
							<input v-model.number="doc.expire_carry_forwarded_leaves_after_days" type="number" min="0" class="form-input w-full" />
							<span class="mt-1 block text-xs text-gray-500">0 = carried days never expire</span></label>
					</div>
				</section>

				<!-- Encashment -->
				<section class="rounded-lg border p-4 space-y-3">
					<Check v-model="doc.allow_encashment" label="Unused days can be paid out (encashment)" />
					<div v-if="doc.allow_encashment" class="grid grid-cols-1 gap-4 sm:grid-cols-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">Most days paid out</span>
							<input v-model.number="doc.max_encashable_leaves" type="number" min="0" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Days that can't be paid out</span>
							<input v-model.number="doc.non_encashable_leaves" type="number" min="0" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Paid through component</span>
							<LinkField v-model="doc.earning_component" doctype="Salary Component" :filters="{ type: 'Earning' }" /></label>
					</div>
				</section>

				<p v-if="isNew" class="text-sm text-gray-500">
					A new type gives nobody days until it is in a leave policy that is assigned (Leave → Setup → New policy, then Assign).
				</p>
			</div>
		</template>
		<template #actions>
			<div class="flex gap-2">
				<Button class="flex-1" label="Cancel" @click="$emit('close')" />
				<Button class="flex-1" variant="solid" :label="isNew ? 'Create leave type' : 'Save'" :loading="saving" :disabled="!doc" @click="save" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, h, ref, watch } from "vue"
import { Dialog, LoadingIndicator, call } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { ok, errorMessages } from "../api"

const props = defineProps({ open: Boolean, name: String })
const emit = defineEmits(["close", "saved"])

const DEFAULTS = {
	doctype: "Leave Type", leave_type_name: "", max_leaves_allowed: 0, max_continuous_days_allowed: 0, applicable_after: 0,
	is_lwp: 0, is_ppl: 0, include_holiday: 0, allow_negative: 0, is_optional_leave: 0, is_compensatory: 0,
	is_earned_leave: 0, earned_leave_frequency: "Monthly", allocate_on_day: "Last Day", rounding: "0.5",
	is_carry_forward: 0, maximum_carry_forwarded_leaves: 0, expire_carry_forwarded_leaves_after_days: 0,
	allow_encashment: 0, max_encashable_leaves: 0, non_encashable_leaves: 0, earning_component: "",
}
const doc = ref(null)
const errors = ref([])
const saving = ref(false)
const isNew = computed(() => !props.name)

const PER_YEAR = { Monthly: 12, Quarterly: 4, "Half-Yearly": 2, Yearly: 1 }
const earnedExample = computed(() => {
	const d = doc.value
	const n = PER_YEAR[d.earned_leave_frequency] || 12
	const period = { Monthly: "month", Quarterly: "quarter", "Half-Yearly": "half-year", Yearly: "year" }[d.earned_leave_frequency] || "month"
	const when = d.allocate_on_day === "Date of Joining" ? `each ${period} on the joining-date anniversary` : `on the ${d.allocate_on_day.toLowerCase()} of each ${period}`
	return `The policy's days a year are split ${n} ways and the scheduler adds a share ${when} — e.g. 22 days a year adds ${(22 / n).toFixed(2).replace(/\.?0+$/, "")}. ` +
		"It only accrues on allocations made by a leave policy assignment, not on ones typed by hand."
})

// A labelled checkbox with a hint underneath (0/1 like Frappe Check fields)
const Check = (p, { emit: e }) =>
	h("label", { class: ["flex items-start gap-2.5 rounded px-1 py-1", p.disabled ? "opacity-50" : "cursor-pointer"] }, [
		h("input", { type: "checkbox", class: "form-checkbox mt-0.5", checked: !!p.modelValue, disabled: p.disabled,
			onChange: (ev) => e("update:modelValue", ev.target.checked ? 1 : 0) }),
		h("span", { class: "text-sm" }, [
			h("span", { class: p.warn && p.modelValue ? "font-medium text-amber-800" : "font-medium text-gray-900" }, p.label),
			p.hint ? h("span", { class: "block text-xs text-gray-500" }, p.hint) : null,
		]),
	])
Check.props = ["modelValue", "label", "hint", "disabled", "warn"]
Check.emits = ["update:modelValue"]

async function load() {
	errors.value = []
	doc.value = null
	doc.value = props.name ? await call("frappe.client.get", { doctype: "Leave Type", name: props.name }) : { ...DEFAULTS }
}

async function save() {
	saving.value = true
	errors.value = []
	try {
		const d = { ...doc.value }
		if (!d.leave_type_name?.trim()) throw { messages: ["Give the leave type a name."] }
		const saved = await call(isNew.value ? "frappe.client.insert" : "frappe.client.save", { doc: d })
		ok(isNew.value ? "Leave type created" : "Leave type saved", saved.name)
		emit("saved", saved.name)
		emit("close")
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		saving.value = false
	}
}

watch(() => props.open, (v) => v && load(), { immediate: true })
</script>
