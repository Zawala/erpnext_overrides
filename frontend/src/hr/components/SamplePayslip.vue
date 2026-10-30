<template>
	<section class="rounded-lg border bg-white">
		<header class="border-b px-4 py-3">
			<h3 class="font-semibold">Sample payslip</h3>
			<p class="text-xs text-gray-500">Worked out by payroll itself from what's on screen. Nothing is saved.</p>
		</header>
		<div class="grid grid-cols-2 gap-3 border-b p-4">
			<label class="col-span-2 sm:col-span-1 xl:col-span-2"><span class="mb-1 block text-xs text-gray-600">Gross (base salary)</span>
				<input v-model.number="gross" type="number" min="0" step="10" inputmode="decimal" class="form-input w-full text-right tabular" /></label>
			<label><span class="mb-1 block text-xs text-gray-600">Month</span>
				<input v-model="month" type="month" class="form-input w-full" /></label>
			<label v-if="structures"><span class="mb-1 block text-xs text-gray-600">Structure</span>
				<select v-model="pickedStructure" class="form-select w-full">
					<option v-for="s in structures" :key="s.name" :value="s.name">{{ s.name }}</option>
				</select></label>
			<label v-else-if="slabs"><span class="mb-1 block text-xs text-gray-600">Tax bands</span>
				<select v-model="pickedSlab" class="form-select w-full">
					<option value="">None</option>
					<option v-for="s in slabs" :key="s.name" :value="s.name">{{ s.name }}</option>
				</select></label>
			<label class="col-span-2"><span class="mb-1 block text-xs text-gray-600">As this employee <span class="text-gray-400">(leave, joining date)</span></span>
				<LinkField v-model="employee" doctype="Employee" :placeholder="out?.employee_name || 'Any employee'" /></label>
		</div>
		<div class="p-4 text-sm" aria-live="polite">
			<div v-if="busy && !out" class="flex items-center gap-2 text-gray-500"><LoadingIndicator class="h-4 w-4" /> Working it out…</div>
			<p v-else-if="out?.error" class="rounded bg-red-50 px-3 py-2 text-red-800">{{ out.error }}</p>
			<template v-else-if="out">
				<dl class="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 tabular" :class="busy ? 'opacity-50' : ''">
					<template v-for="l in shownLines" :key="l.component">
						<dt :class="l.kind === 'employer' ? 'text-gray-400' : 'text-gray-600'">
							{{ l.kind === "deduction" ? "− " : "" }}{{ l.component }}<span v-if="l.kind === 'employer'"> (employer)</span>
						</dt>
						<dd class="text-right" :class="l.kind === 'employer' ? 'text-gray-400' : ''">{{ m(l.amount) }}</dd>
					</template>
					<dt class="mt-1 border-t pt-1 text-gray-600">Gross pay</dt>
					<dd class="mt-1 border-t pt-1 text-right">{{ m(out.gross) }}</dd>
					<dt class="font-semibold">Net pay</dt>
					<dd class="text-right font-semibold">{{ m(out.net) }}</dd>
				</dl>
				<p v-if="compare && compare.net !== undefined && Math.abs(out.net - compare.net) >= 0.005" class="mt-2 rounded px-2 py-1 text-xs"
					:class="out.net > compare.net ? 'bg-green-50 text-green-800' : 'bg-amber-50 text-amber-800'">
					{{ out.net > compare.net ? "+" : "−" }}{{ m(Math.abs(out.net - compare.net)) }} take-home compared with what's saved ({{ m(compare.net) }})
				</p>
				<p class="mt-2 text-xs text-gray-400">{{ out.employee_name }} · {{ monthLabel }}</p>
			</template>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { LoadingIndicator } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { money } from "@/utils/format"
import { boot } from "@/boot"
import { pay } from "../api"

// draft: what's being edited ({rows} or a slab); saved: the stored version to compare with
const props = defineProps({
	draftStructure: Object, structureName: String, draftSlab: Object, slabName: String,
	structures: Array, slabs: Array, defaultStructure: String, defaultSlab: String,
})

const gross = ref(1000)
const now = new Date()
const month = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`)
const employee = ref("")
const pickedStructure = ref(props.defaultStructure || "")
const pickedSlab = ref(props.defaultSlab || "")
const out = ref(null)
const compare = ref(null)
const busy = ref(false)

const m = (v) => money(v || 0, boot.currency)
const monthLabel = computed(() => new Date(`${month.value}-01T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" }))
// earnings, then deductions, then employer costs: the order of a payslip
const ORDER = { earning: 0, deduction: 1, employer: 2 }
const shownLines = computed(() => [...(out.value?.lines || [])].sort((a, b) => ORDER[a.kind] - ORDER[b.kind]))

watch(() => props.defaultStructure, (v) => v && !pickedStructure.value && (pickedStructure.value = v))
watch(() => props.defaultSlab, (v) => v && !pickedSlab.value && (pickedSlab.value = v))

function args(draft) {
	const a = { gross: gross.value || 0, month: `${month.value}-01`, employee: employee.value || undefined }
	if (props.structures) a.structure_name = pickedStructure.value
	else if (draft && props.draftStructure) a.structure = props.draftStructure
	else a.structure_name = props.structureName
	if (props.slabs) a.slab_name = pickedSlab.value || undefined
	else if (draft && props.draftSlab) a.slab = props.draftSlab
	else a.slab_name = props.slabName
	return a
}

let timer = null
let seq = 0
function schedule() {
	clearTimeout(timer)
	timer = setTimeout(run, 400)
}
async function run() {
	const mine = ++seq
	busy.value = true
	try {
		// the stored version of what's being edited, if there is one, to show the difference
		const savedName = props.draftStructure ? props.structureName : props.draftSlab ? props.slabName : null
		const [draft, saved] = await Promise.all([
			pay("preview", args(true)),
			savedName ? pay("preview", args(false)) : Promise.resolve(null),
		])
		if (mine !== seq) return // edited again meanwhile
		out.value = draft
		compare.value = saved && !saved.error ? saved : null
	} catch (e) {
		if (mine === seq) out.value = { error: e.messages?.[0] || "Could not work it out" }
	} finally {
		if (mine === seq) busy.value = false
	}
}

watch(() => [props.draftStructure, props.draftSlab, props.structureName, props.slabName, gross.value, month.value,
	employee.value, pickedStructure.value, pickedSlab.value], schedule, { deep: true, immediate: true })
</script>
