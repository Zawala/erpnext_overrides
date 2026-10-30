<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Export data" subtitle="Download records as Excel or CSV, in the layout Import data reads back." back="/data" />

		<div class="mx-auto w-full max-w-[1200px] space-y-4 p-4 pb-28 lg:p-6 lg:pb-28">
			<Steps :steps="STEPS" :current="step" @go="(i) => (step = i)" />

			<!-- 1. What -->
			<section v-if="step === 0" class="space-y-3">
				<h2 class="text-base font-semibold">What do you want to export?</h2>
				<RecordTypePicker :model-value="doctype" mode="export" @update:model-value="pick" />
			</section>

			<!-- 2. Which records -->
			<section v-else-if="step === 1 && type" class="space-y-3">
				<h2 class="text-base font-semibold">Which {{ type.label.toLowerCase() }}?</h2>
				<div class="grid gap-3 sm:grid-cols-2">
					<button class="rounded-lg border bg-white p-4 text-left hover:border-gray-400" :class="!some && 'border-gray-900 ring-1 ring-gray-900'" @click="some = false">
						<div class="font-medium">All of them</div>
						<p class="mt-1 text-sm text-gray-600">{{ type.count.toLocaleString() }} {{ type.label.toLowerCase() }}.</p>
					</button>
					<button class="rounded-lg border bg-white p-4 text-left hover:border-gray-400" :class="some && 'border-gray-900 ring-1 ring-gray-900'" @click="some = true">
						<div class="font-medium">Only some</div>
						<p class="mt-1 text-sm text-gray-600">Choose by group, status, date or any other field.</p>
					</button>
				</div>
				<div v-if="some" class="space-y-2 rounded-lg border bg-white p-4">
					<div v-for="(f, i) in filters" :key="i" class="flex flex-wrap items-center gap-2">
						<span class="w-10 text-sm text-gray-500">{{ i ? "and" : "Where" }}</span>
						<select v-model="f.field" class="form-select w-full sm:w-56" aria-label="Field">
							<option v-for="c in filterFields" :key="c.key" :value="c.key">{{ c.label }}</option>
						</select>
						<select v-model="f.op" class="form-select w-full sm:w-40" aria-label="Condition">
							<option v-for="o in opsFor(f.field)" :key="o.value" :value="o.value">{{ o.label }}</option>
						</select>
						<div v-if="f.op !== 'is'" class="w-full sm:w-60">
							<LinkField v-if="fieldOf(f.field)?.fieldtype === 'Link'" v-model="f.value" :doctype="fieldOf(f.field).options" />
							<select v-else-if="fieldOf(f.field)?.fieldtype === 'Check'" v-model="f.value" class="form-select w-full">
								<option value="1">Yes (ticked)</option><option value="0">No</option>
							</select>
							<select v-else-if="fieldOf(f.field)?.fieldtype === 'Select'" v-model="f.value" class="form-select w-full">
								<option v-for="o in (fieldOf(f.field).options || '').split('\n')" :key="o" :value="o">{{ o || "(blank)" }}</option>
							</select>
							<input v-else v-model="f.value" class="form-input w-full" :type="['Date', 'Datetime'].includes(fieldOf(f.field)?.fieldtype) ? 'date' : 'text'" aria-label="Value" />
						</div>
						<select v-else v-model="f.value" class="form-select w-full sm:w-40" aria-label="Set or not set">
							<option value="set">filled in</option><option value="not set">blank</option>
						</select>
						<button class="rounded p-1 text-gray-500 hover:bg-gray-100" aria-label="Remove condition" @click="filters.splice(i, 1)"><FeatherIcon name="x" class="h-4 w-4" /></button>
					</div>
					<Button v-if="filters.length < 3" size="sm" icon-left="plus" label="Add a condition" @click="addFilter" />
				</div>
				<div class="flex flex-wrap items-center justify-end gap-3">
					<span class="text-sm text-gray-600"><LoadingIndicator v-if="counting" class="inline h-4 w-4" /><template v-else-if="count === 0"><span class="text-amber-800">Nothing matches: change the conditions.</span></template><template v-else-if="count !== null"><b>{{ count.toLocaleString() }}</b> to export</template></span>
					<Button variant="solid" label="Next" icon-right="arrow-right" :disabled="!count" @click="step = 2" />
				</div>
			</section>

			<!-- 3. Which columns -->
			<section v-else-if="step === 2 && type" class="space-y-3">
				<h2 class="text-base font-semibold">Which columns?</h2>
				<div class="flex flex-wrap items-center gap-3">
					<Chips :model-value="preset" :options="PRESETS" @update:model-value="usePreset" />
					<input v-model="colSearch" class="form-input w-full sm:w-60" placeholder="Find a column" aria-label="Find a column" />
				</div>
				<label class="flex items-start gap-2 rounded-lg border bg-white p-3 text-sm">
					<input v-model="withId" type="checkbox" class="form-checkbox mt-0.5" />
					<span><b>Include the {{ type.id_label }} column</b>
						<span class="block text-gray-600">Keep this on if you will change the file and import it back to update these records.</span></span>
				</label>
				<div v-for="t in type.tables" :key="t.key" class="rounded-lg border bg-white">
					<div class="flex items-center gap-3 border-b px-4 py-2.5">
						<h3 class="min-w-0 flex-1 font-medium">{{ t.label }}<span v-if="t.key !== type.doctype" class="ml-1 text-xs font-normal text-gray-500">table: several rows per record</span></h3>
						<span class="text-xs text-gray-500">{{ t.columns.filter((c) => chosen.has(c.key)).length }} chosen</span>
					</div>
					<div class="grid gap-x-4 gap-y-1 p-3 sm:grid-cols-2 lg:grid-cols-3">
						<label v-for="c in visibleColumns(t)" :key="c.key" class="flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-gray-50">
							<input type="checkbox" class="form-checkbox" :checked="chosen.has(c.key)" @change="toggle(c.key)" />
							<span class="truncate">{{ c.label }}</span><span v-if="c.required" class="text-xs text-gray-400">required</span>
						</label>
						<span v-if="!visibleColumns(t).length" class="text-sm text-gray-400">No matching columns.</span>
					</div>
				</div>
				<div class="flex flex-wrap items-center justify-end gap-3">
					<span class="text-sm text-gray-600">{{ chosen.size }} column{{ chosen.size === 1 ? "" : "s" }}</span>
					<Button variant="solid" label="Next" icon-right="arrow-right" :disabled="!chosen.size" @click="step = 3" />
				</div>
			</section>

			<!-- 4. Download -->
			<section v-else-if="step === 3 && type" class="space-y-3">
				<h2 class="text-base font-semibold">Download</h2>
				<div class="grid gap-3 sm:grid-cols-2">
					<button v-for="f in FORMATS" :key="f.value" class="rounded-lg border bg-white p-4 text-left hover:border-gray-400"
						:class="fmt === f.value && 'border-gray-900 ring-1 ring-gray-900'" @click="fmt = f.value">
						<div class="font-medium">{{ f.label }}</div>
						<p class="mt-1 text-sm text-gray-600">{{ f.text }}</p>
					</button>
				</div>
				<div class="rounded-lg border bg-white p-4 text-sm">
					<b>{{ (count ?? type.count).toLocaleString() }}</b> {{ type.label.toLowerCase() }} × <b>{{ chosen.size + (withId ? 1 : 0) }}</b> columns
					<span v-if="some && activeFilters.length" class="text-gray-600"> · {{ activeFilters.length }} condition{{ activeFilters.length === 1 ? "" : "s" }}</span>
					<p class="mt-1 text-gray-600">To update records with this file: change the cells you need, keep the {{ type.id_label }} column and the headings, then use <router-link class="text-blue-700 hover:underline" :to="{ path: '/data/import', query: { type: doctype } }">Import data → Update existing records</router-link>.</p>
				</div>
				<div class="flex justify-end"><Button variant="solid" icon-left="download" label="Download" @click="go" /></div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { FeatherIcon, LoadingIndicator, debounce } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import LinkField from "@/components/LinkField.vue"
import Steps from "../components/Steps.vue"
import RecordTypePicker from "../components/RecordTypePicker.vue"
import { adm, download, fail, ok } from "../api"

const STEPS = ["What", "Which records", "Which columns", "Download"]
const PRESETS = [
	{ value: "essentials", label: "Essentials" },
	{ value: "main", label: "Every field of the record" },
	{ value: "all", label: "Everything, with tables" },
]
const FORMATS = [
	{ value: "Excel", label: "Excel (.xlsx) · recommended", text: "Opens straight in Excel with dates, numbers and leading zeros kept as they are." },
	{ value: "CSV", label: "CSV", text: "Plain text for other systems. Excel may reformat dates and codes when it opens one." },
]
const OPS = {
	text: [{ value: "=", label: "is" }, { value: "!=", label: "is not" }, { value: "like", label: "contains" }, { value: "is", label: "is…" }],
	number: [{ value: "=", label: "=" }, { value: ">", label: "more than" }, { value: "<", label: "less than" }, { value: "is", label: "is…" }],
	date: [{ value: ">=", label: "on or after" }, { value: "<=", label: "on or before" }, { value: "=", label: "on" }, { value: "is", label: "is…" }],
	pick: [{ value: "=", label: "is" }, { value: "!=", label: "is not" }, { value: "is", label: "is…" }],
}

const route = useRoute()
const step = ref(0)
const doctype = ref(route.query.type || "")
const type = ref(null)
const some = ref(false)
const filters = ref([])
const count = ref(null)
const counting = ref(false)
const chosen = ref(new Set())
const preset = ref("essentials")
const colSearch = ref("")
const withId = ref(true)
const fmt = ref("Excel")

async function pick(dt) {
	doctype.value = dt
	try {
		type.value = await adm("get_data_type", { doctype: dt })
		some.value = false
		filters.value = []
		usePreset("essentials")
		count.value = type.value.count
		step.value = 1
	} catch (e) {
		fail(e)
	}
}
if (doctype.value) pick(doctype.value)

const filterFields = computed(() => type.value.tables[0].columns.filter((c) => !["Table", "Table MultiSelect", "Attach", "Attach Image", "Text Editor", "Code"].includes(c.fieldtype)))
const fieldOf = (key) => type.value.tables[0].columns.find((c) => c.key === key)
function opsFor(key) {
	const t = fieldOf(key)?.fieldtype
	if (["Date", "Datetime"].includes(t)) return OPS.date
	if (["Int", "Float", "Currency", "Percent"].includes(t)) return OPS.number
	if (["Link", "Select", "Check"].includes(t)) return OPS.pick
	return OPS.text
}
function addFilter() {
	const first = filterFields.value.find((c) => c.fieldtype === "Link") || filterFields.value[0]
	filters.value.push({ field: first.key, op: "=", value: "" })
}
watch(some, (v) => v && !filters.value.length && addFilter())

const activeFilters = computed(() => (some.value ? filters.value.filter((f) => f.op === "is" ? f.value : f.value !== "").map((f) => [f.field, f.op, f.value]) : []))
const recount = debounce(async () => {
	counting.value = true
	try {
		count.value = await adm("count_records", { doctype: doctype.value, filters: activeFilters.value })
	} catch (e) {
		fail(e, "Could not count")
	} finally {
		counting.value = false
	}
}, 300)
watch([activeFilters, some], () => type.value && recount(), { deep: true })
// a condition's value must suit its field: reset it when the field or condition changes
watch(() => filters.value.map((f) => `${f.field}|${f.op}`), (now, before) => {
	now.forEach((k, i) => {
		if (before && before[i] && before[i] !== k) {
			const f = filters.value[i]
			if (!opsFor(f.field).some((o) => o.value === f.op)) f.op = opsFor(f.field)[0].value
			f.value = f.op === "is" ? "set" : ""
		}
	})
})

function usePreset(p) {
	preset.value = p
	const tables = type.value.tables
	const keys = p === "essentials" ? tables.flatMap((t) => t.columns.filter((c) => c.essential).map((c) => c.key))
		: p === "main" ? tables[0].columns.map((c) => c.key)
		: tables.flatMap((t) => t.columns.map((c) => c.key))
	chosen.value = new Set(keys)
}
function toggle(key) {
	const s = new Set(chosen.value)
	s.has(key) ? s.delete(key) : s.add(key)
	chosen.value = s
	preset.value = ""
}
const visibleColumns = (t) => {
	const q = colSearch.value.trim().toLowerCase()
	return q ? t.columns.filter((c) => c.label.toLowerCase().includes(q) || c.key.includes(q)) : t.columns
}

function go() {
	download("export_data", { doctype: doctype.value, columns: [...chosen.value], filters: activeFilters.value, fmt: fmt.value, with_id: withId.value ? 1 : 0 })
	ok("Export started", "Your browser saves the file when it's ready.")
}
</script>
