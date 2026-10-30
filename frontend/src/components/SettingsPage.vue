<template>
	<div class="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-4 p-4 pb-28 lg:grid-cols-[minmax(0,1fr)_400px] lg:p-6 lg:pb-28 items-start">
		<!-- Settings -->
		<div class="space-y-4">
			<div v-if="!settings" class="rounded-lg border bg-white p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<slot name="before" />
			<section v-for="s in (settings?.sections || []).filter((s) => !hideSections.includes(s.label))" :key="s.label" class="rounded-lg border bg-white">
				<h3 class="border-b px-4 py-3 font-semibold">{{ s.label }}</h3>
				<div class="grid grid-cols-1 gap-x-6 gap-y-4 p-4 sm:grid-cols-2">
					<template v-for="f in s.fields" :key="f.doctype + f.fieldname">
						<!-- Yes / no -->
						<label v-if="f.type === 'Check'" class="flex cursor-pointer items-start gap-3 sm:col-span-2">
							<input type="checkbox" class="form-checkbox mt-0.5" :checked="!!Number(val(f))" @change="set(f, $event.target.checked ? 1 : 0)" />
							<span class="text-sm">
								<span :class="dirty(f) ? 'font-medium text-blue-800' : 'text-gray-800'">{{ f.label }}</span>
								<span v-if="f.description" class="block text-xs text-gray-500">{{ f.description }}</span>
							</span>
						</label>

						<!-- A table (e.g. petty cash boxes) -->
						<div v-else-if="f.type === 'Table'" class="sm:col-span-2">
							<div class="mb-1.5 text-sm" :class="dirty(f) ? 'font-medium text-blue-800' : 'text-gray-600'">{{ f.label }}</div>
							<div class="space-y-2">
								<div v-for="(row, i) in val(f)" :key="row.name || i" class="rounded border p-3">
									<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
										<Field v-for="c in f.columns" :key="c.fieldname" :field="asField(c)" :doc="row"
											@change="(fn, v) => setRow(f, i, fn, v)" />
									</div>
									<button class="mt-2 text-xs text-red-700 hover:underline" @click="removeRow(f, i)">Remove</button>
								</div>
								<button class="text-sm text-blue-700 hover:underline" @click="addRow(f)">+ Add a row</button>
							</div>
						</div>

						<div v-else :class="dirty(f) ? '[&_label]:font-medium [&_label]:text-blue-800' : ''">
							<Field :field="asField(f)" :doc="{ [f.fieldname]: val(f) }" @change="(_fn, v) => set(f, v)" />
						</div>
					</template>
				</div>
			</section>
		</div>

		<!-- Who changed what -->
		<section class="rounded-lg border bg-white lg:sticky lg:top-20">
			<header class="space-y-2 border-b px-4 py-3">
				<h3 class="font-semibold">Who changed what</h3>
				<Chips v-if="settings" v-model="section" :options="[{ value: '', label: 'All' }, ...settings.sections.map((s) => ({ value: s.label, label: s.label }))]" />
			</header>
			<div v-if="!history" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<p v-else-if="!history.length" class="px-4 py-6 text-sm text-gray-500">No changes recorded yet.</p>
			<ul v-else class="max-h-[70vh] divide-y overflow-y-auto">
				<li v-for="(h, i) in history" :key="h.version + i" class="flex gap-3 px-4 py-2.5 text-sm">
					<div class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gray-100 text-xs font-medium text-gray-600">{{ initials(h.by) }}</div>
					<div class="min-w-0">
						<div>
							<b class="font-medium">{{ h.by }}</b>
							<template v-if="h.kind === 'changed'"> changed <i>{{ h.setting }}</i> from <span class="tabular">{{ h.old }}</span> → <span class="tabular font-medium">{{ h.new }}</span></template>
							<template v-else-if="h.kind === 'row_changed'"> changed <i>{{ h.field }}</i> on {{ h.row }} from <span class="tabular">{{ h.old }}</span> → <span class="tabular font-medium">{{ h.new }}</span></template>
							<template v-else>{{ ` ${h.kind} ${h.row || "a row"} in ` }}<i>{{ h.setting }}</i></template>
						</div>
						<div class="text-xs text-gray-500">{{ h.section }} · {{ relative(h.when) }}</div>
					</div>
				</li>
			</ul>
			<div v-if="nextStart !== null && history?.length" class="border-t p-2 text-center">
				<Button size="sm" label="Load more" :loading="loadingHistory" @click="loadHistory(true)" />
			</div>
		</section>

		<!-- Save bar -->
		<div v-if="changes.length" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
				<div class="min-w-0 flex-1 text-sm">
					<b>{{ changes.length }} unsaved change{{ changes.length === 1 ? "" : "s" }}</b>
					<span class="hidden text-gray-500 sm:inline"> — {{ changes.map((c) => c.label).join(", ") }}</span>
				</div>
				<Button label="Discard" @click="discard" />
				<Button variant="solid" :label="`Save changes (${changes.length})`" :loading="saving" @click="save" />
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { LoadingIndicator, call, toast } from "frappe-ui"
import { relative } from "@/utils/format"
import { errorMessages } from "@/utils/api"
import Field from "./Field.vue"
import Chips from "@/hr/components/Chips.vue"

// Managers' settings for one app (sales, hr or accounts); the backend checks the role
// hideSections: edited elsewhere on the page (their changes still show in the history)
const props = defineProps({ app: { type: String, required: true }, hideSections: { type: Array, default: () => [] } })
const API = "erp_overrides.api.app_settings"

const settings = ref(null)
const edits = reactive({}) // "doctype/fieldname" → new value
const saving = ref(false)
const history = ref(null)
const nextStart = ref(null)
const section = ref("")
const loadingHistory = ref(false)

const key = (f) => `${f.doctype}/${f.fieldname}`
const val = (f) => (key(f) in edits ? edits[key(f)] : f.value)
const dirty = (f) => key(f) in edits
const initials = (n) => String(n || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()
const asField = (f) => ({ fieldname: f.fieldname, label: f.label, type: ["Small Text", "Text", "Long Text"].includes(f.type) ? "Text" : f.type,
	options: f.options, help: f.description, reqd: f.reqd, filters: f.filters ? () => f.filters : undefined })

const fields = computed(() => (settings.value?.sections || []).flatMap((s) => s.fields))
const changes = computed(() => fields.value.filter(dirty).map((f) => ({ doctype: f.doctype, fieldname: f.fieldname, value: edits[key(f)], label: f.label })))

function set(f, v) {
	const same = f.type === "Check" ? Number(f.value || 0) === Number(v) : String(f.value ?? "") === String(v ?? "")
	if (same) delete edits[key(f)]
	else edits[key(f)] = v
}

function rows(f) {
	if (!(key(f) in edits)) edits[key(f)] = f.value.map((r) => ({ ...r }))
	return edits[key(f)]
}
const setRow = (f, i, fieldname, v) => (rows(f)[i][fieldname] = v)
const addRow = (f) => rows(f).push(Object.fromEntries(f.columns.map((c) => [c.fieldname, c.type === "Check" ? 0 : ""])))
const removeRow = (f, i) => rows(f).splice(i, 1)

function discard() {
	for (const k of Object.keys(edits)) delete edits[k]
}

async function load() {
	try {
		settings.value = await call(`${API}.get_settings`, { app: props.app })
	} catch (e) {
		toast({ title: "Could not load settings", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600" })
	}
}

async function loadHistory(more = false) {
	loadingHistory.value = true
	try {
		const res = await call(`${API}.get_history`, { app: props.app, section: section.value || undefined, start: more ? nextStart.value : 0 })
		history.value = more ? [...history.value, ...res.entries] : res.entries
		nextStart.value = res.next_start
	} catch {
		history.value = []
	} finally {
		loadingHistory.value = false
	}
}

async function save() {
	saving.value = true
	try {
		settings.value = await call(`${API}.save_settings`, { app: props.app, changes: changes.value.map(({ label, ...c }) => c) })
		discard()
		toast({ title: "Settings saved", icon: "check", iconClasses: "text-green-600" })
		loadHistory()
	} catch (e) {
		toast({ title: "Not saved", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600", timeout: 10 })
	} finally {
		saving.value = false
	}
}

watch(section, () => loadHistory())
defineExpose({ reload: () => (load(), loadHistory()) })
load()
loadHistory()
</script>
