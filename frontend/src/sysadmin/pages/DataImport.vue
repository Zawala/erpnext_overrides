<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Import data" subtitle="Six short steps. Nothing is saved to your records until the last one." back="/data" />

		<div class="mx-auto w-full max-w-[1200px] space-y-4 p-4 pb-28 lg:p-6 lg:pb-28">
			<Steps :steps="STEPS" :current="step" :locked="running" @go="go" />

			<!-- 1. What -->
			<section v-if="step === 0" class="space-y-3">
				<h2 class="text-base font-semibold">What are you importing?</h2>
				<RecordTypePicker :model-value="doctype" mode="import" @update:model-value="pick" />
			</section>

			<!-- 2. New or update -->
			<section v-else-if="step === 1 && type" class="space-y-3">
				<h2 class="text-base font-semibold">Are these new {{ type.label.toLowerCase() }}, or changes to ones already in the system?</h2>
				<div class="grid gap-3 sm:grid-cols-2">
					<button v-for="m in MODES" :key="m.value" class="rounded-lg border bg-white p-4 text-left hover:border-gray-400"
						:class="mode === m.value && 'border-gray-900 ring-1 ring-gray-900'" @click="mode = m.value">
						<div class="flex items-center gap-2 font-medium"><FeatherIcon :name="m.icon" class="h-4 w-4" /> {{ m.title }}</div>
						<p class="mt-1 text-sm text-gray-600">{{ m.text(type) }}</p>
					</button>
				</div>
				<div v-if="mode === UPDATE" class="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
					Each row finds its record by the <b>{{ type.id_label }}</b> column. The easy way: export the {{ type.label.toLowerCase() }} you want
					to change, edit the file, and upload it here. Columns you leave out are not touched.
					<div class="mt-2"><Button label="Export them first" icon-left="download" @click="$router.push({ path: '/data/export', query: { type: doctype } })" /></div>
				</div>
				<label v-if="type.submittable" class="flex items-start gap-2 rounded-lg border bg-white p-3 text-sm">
					<input v-model="submitAfter" type="checkbox" class="form-checkbox mt-0.5" />
					<span><b>Submit each {{ type.doctype }} after importing it.</b>
						<span class="block text-gray-600">Submitted entries post to the books straight away. Leave this off to import them as drafts and check them in desk first.</span></span>
				</label>
				<div class="flex justify-end"><Button variant="solid" label="Next" icon-right="arrow-right" :disabled="!mode" @click="step = 2" /></div>
			</section>

			<!-- 3. Template and rules -->
			<section v-else-if="step === 2 && type" class="space-y-3">
				<h2 class="text-base font-semibold">Get your file ready</h2>
				<div class="grid gap-3 lg:grid-cols-2">
					<div class="space-y-3 rounded-lg border bg-white p-4">
						<h3 class="font-medium">Start from the template</h3>
						<p class="text-sm text-gray-600">An Excel file with the right column headings for {{ type.label.toLowerCase() }}{{ mode === UPDATE ? `, including ${type.id_label}` : "" }}.
							Fill in one row per record, keep the headings as they are, and save it as Excel or CSV.</p>
						<Button icon-left="download" label="Download template" @click="template" />
						<p v-if="mode === UPDATE" class="text-sm text-gray-600">Or <a class="text-blue-700 hover:underline" href="#" @click.prevent="exportExisting">download your existing {{ type.label.toLowerCase() }}</a> with their {{ type.id_label }} and change them.</p>
					</div>
					<div class="space-y-2 rounded-lg border bg-white p-4 text-sm">
						<h3 class="font-medium">Before you upload, check</h3>
						<ul class="space-y-1.5">
							<li v-if="mode === INSERT && type.required.length" class="flex gap-2"><FeatherIcon name="check-square" class="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
								<span>Every row has <b>{{ type.required.join(", ") }}</b>.</span></li>
							<li v-for="r in type.rules" :key="r" class="flex gap-2"><FeatherIcon name="check-square" class="mt-0.5 h-4 w-4 shrink-0 text-gray-500" /> <span>{{ r }}</span></li>
							<li class="flex gap-2"><FeatherIcon name="check-square" class="mt-0.5 h-4 w-4 shrink-0 text-gray-500" /> <span>Values from lists (groups, territories, units…) are spelt as they are in the system. If one isn't, the next steps let you pick the right one.</span></li>
							<li class="flex gap-2"><FeatherIcon name="check-square" class="mt-0.5 h-4 w-4 shrink-0 text-gray-500" /> <span>Dates are written as YYYY-MM-DD.</span></li>
						</ul>
					</div>
				</div>
				<div class="flex justify-end"><Button variant="solid" label="My file is ready" icon-right="arrow-right" @click="step = 3" /></div>
			</section>

			<!-- 4. Upload -->
			<section v-else-if="step === 3" class="space-y-3">
				<h2 class="text-base font-semibold">Upload your file</h2>
				<label class="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed bg-white px-4 py-10 text-center hover:bg-gray-50"
					:class="dragging && 'border-gray-900 bg-gray-50'" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="drop">
					<input type="file" accept=".csv,.xlsx" class="hidden" @change="(e) => upload(e.target.files[0], e)" />
					<LoadingIndicator v-if="reading" class="h-6 w-6 text-gray-500" />
					<FeatherIcon v-else name="upload-cloud" class="h-8 w-8 text-gray-400" />
					<span class="font-medium">{{ reading ? "Reading your file…" : "Drop a CSV or Excel file here, or click to choose one" }}</span>
					<span class="text-sm text-gray-500">{{ type?.label }} · {{ mode === UPDATE ? "update existing" : "add new" }}</span>
				</label>
			</section>

			<!-- 5. Check -->
			<section v-else-if="step === 4 && check" class="space-y-4">
				<div class="rounded-lg border p-4" :class="check.ready ? 'border-green-300 bg-green-50' : 'border-amber-300 bg-amber-50'">
					<div class="flex items-start gap-3">
						<FeatherIcon :name="check.ready ? 'check-circle' : 'alert-triangle'" class="mt-0.5 h-5 w-5 shrink-0" :class="check.ready ? 'text-green-700' : 'text-amber-700'" />
						<div class="text-sm">
							<div class="font-medium">{{ check.ready ? "Ready to import" : `${todo} thing${todo === 1 ? "" : "s"} to sort out first` }}</div>
							<div class="text-gray-700"><b>{{ check.filename }}</b> holds {{ check.records }} {{ check.doctype }} record{{ check.records === 1 ? "" : "s" }}
								({{ check.rows }} row{{ check.rows === 1 ? "" : "s" }})<template v-if="check.skipped_rows.length">; {{ check.skipped_rows.length }} row{{ check.skipped_rows.length === 1 ? " is" : "s are" }} left out</template>.</div>
						</div>
						<LoadingIndicator v-if="saving" class="ml-auto h-4 w-4 text-gray-500" />
					</div>
				</div>

				<!-- Must fix -->
				<div v-if="check.must_fix.length" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold text-red-800">Fix these</h3>
					<ul class="divide-y text-sm">
						<li v-for="(p, i) in check.must_fix" :key="i" class="flex flex-wrap items-center gap-3 px-4 py-2.5">
							<span class="min-w-0 flex-1"><b v-if="p.row" class="mr-1">Row {{ p.row }}:</b>{{ p.message }}</span>
							<Button v-if="p.row" size="sm" label="Leave this row out" @click="toggleRow(p.row)" />
						</li>
					</ul>
					<p class="border-t px-4 py-2 text-xs text-gray-500">Fix the file and upload it again, or change the columns below.</p>
				</div>

				<!-- Values that don't exist -->
				<div v-if="check.values.length" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Values not found in the system</h3>
					<p class="px-4 pt-3 text-sm text-gray-600">Pick what each one should be, or leave its rows out. Your file isn't changed; the choice applies to this import.</p>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="text-left text-xs uppercase tracking-wide text-gray-500">
								<tr><th class="px-4 py-2 font-medium">Column</th><th class="px-2 py-2 font-medium">In your file</th><th class="px-2 py-2 font-medium">Rows</th><th class="px-4 py-2 font-medium">Use instead</th></tr>
							</thead>
							<tbody>
								<tr v-for="v in check.values" :key="v.id" class="border-t align-top" :class="isLeftOut(v) && 'text-gray-400'">
									<td class="px-4 py-2">{{ v.column }}</td>
									<td class="px-2 py-2 font-medium">“{{ v.source }}”</td>
									<td class="px-2 py-2 tabular">{{ v.rows.join(", ") }}</td>
									<td class="px-4 py-2">
										<div class="flex flex-wrap items-center gap-2">
											<div v-if="!isLeftOut(v)" class="w-full sm:w-64">
												<LinkField v-if="v.fieldtype === 'Link'" :model-value="v.target" :doctype="v.link_doctype" :placeholder="`Pick a ${v.link_doctype}`" @update:model-value="(x) => setValue(v, x)" />
												<select v-else class="form-select w-full" :value="v.target" @change="(e) => setValue(v, e.target.value)">
													<option value="">Pick one</option>
													<option v-for="o in v.options" :key="o" :value="o">{{ o }}</option>
												</select>
											</div>
											<button class="text-xs text-gray-600 underline" @click="toggleRow(...v.rows)">{{ isLeftOut(v) ? "Put the rows back" : "Leave these rows out" }}</button>
											<FeatherIcon v-if="v.target && !isLeftOut(v)" name="check" class="h-4 w-4 text-green-600" />
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>

				<!-- Columns -->
				<div class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Where each column goes</h3>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="text-left text-xs uppercase tracking-wide text-gray-500">
								<tr><th class="px-4 py-2 font-medium">Your column</th><th class="px-2 py-2 font-medium">Goes into</th><th class="px-4 py-2 font-medium">First value</th></tr>
							</thead>
							<tbody>
								<tr v-for="(c, i) in check.columns" :key="c.index" class="border-t">
									<td class="px-4 py-2 font-medium">{{ c.header || "(no heading)" }}</td>
									<td class="px-2 py-1.5">
										<select class="form-select w-full sm:w-72" :class="c.state === 'unmatched' && 'border-amber-400'" :value="c.key || (c.state === 'left_out' ? DONT : '')"
											:aria-label="`Where ${c.header} goes`" @change="(e) => setColumn(c, e.target.value)">
											<option v-if="c.state === 'unmatched'" value="" disabled>Not matched: pick a field</option>
											<option :value="DONT">Leave this column out</option>
											<optgroup v-for="g in fieldGroups" :key="g.label" :label="g.label">
												<option v-for="f in g.fields" :key="f.key" :value="f.key">{{ f.label }}{{ f.required ? " *" : "" }}</option>
											</optgroup>
										</select>
										<div v-if="c.state === 'unmatched'" class="mt-1 text-xs text-amber-800">No field is called “{{ c.header }}”: pick one, or it is left out.</div>
									</td>
									<td class="max-w-[240px] truncate px-4 py-2 text-gray-600">{{ firstValue(i) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
					<p class="border-t px-4 py-2 text-xs text-gray-500">* required for a new {{ check.doctype }}.</p>
				</div>

				<details class="rounded-lg border bg-white">
					<summary class="cursor-pointer px-4 py-3 text-sm font-medium">The first {{ check.sample.length }} rows as they will be read</summary>
					<div class="overflow-x-auto border-t">
						<table class="w-full text-sm">
							<thead class="bg-gray-50 text-left text-xs text-gray-500"><tr><th v-for="c in check.columns" :key="c.index" class="whitespace-nowrap px-3 py-2 font-medium">{{ c.label || c.header }}</th></tr></thead>
							<tbody><tr v-for="(r, i) in check.sample" :key="i" class="border-t"><td v-for="(v, j) in r" :key="j" class="whitespace-nowrap px-3 py-1.5" :class="check.columns[j]?.state !== 'matched' && 'text-gray-400 line-through'">{{ v }}</td></tr></tbody>
						</table>
					</div>
				</details>

				<details v-if="check.notes.length" class="rounded-lg border bg-white">
					<summary class="cursor-pointer px-4 py-3 text-sm font-medium">{{ check.notes.length }} note{{ check.notes.length === 1 ? "" : "s" }} (these don't stop the import)</summary>
					<ul class="space-y-1 border-t px-4 py-3 text-sm text-gray-700"><li v-for="(n, i) in check.notes" :key="i"><b v-if="n.row">Row {{ n.row }}: </b>{{ n.message }}</li></ul>
				</details>
			</section>

			<!-- 6. Import -->
			<section v-else-if="step === 5" class="space-y-4">
				<div v-if="!result || inFlight" class="space-y-3 rounded-lg border bg-white p-6 text-center">
					<LoadingIndicator class="inline h-6 w-6 text-gray-500" />
					<div class="font-medium">{{ result?.status === "In Progress" ? `Importing… ${result.done} of ${result.total}` : "Starting the import…" }}</div>
					<div v-if="result?.total" class="mx-auto h-2 max-w-md rounded bg-gray-200"><div class="h-2 rounded bg-gray-900 transition-all" :style="{ width: `${(100 * result.done) / result.total}%` }" /></div>
					<p class="text-sm text-gray-500">You can leave this page: the import carries on and shows under Import history.</p>
				</div>
				<template v-else>
					<div v-if="result.blocked.length" class="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">
						<div class="font-medium">The import didn't start</div>
						<ul class="mt-1 list-disc pl-5"><li v-for="b in result.blocked" :key="b">{{ b }}</li></ul>
						<Button class="mt-3" label="Back to the check" @click="reopenCheck" />
					</div>
					<div v-else class="rounded-lg border p-4" :class="result.failed.length ? (result.succeeded ? 'border-amber-300 bg-amber-50' : 'border-red-300 bg-red-50') : 'border-green-300 bg-green-50'">
						<div class="text-base font-semibold">{{ headline }}</div>
						<p class="mt-1 text-sm"><b>{{ result.succeeded }}</b> of {{ result.total }} {{ result.doctype }} record{{ result.total === 1 ? "" : "s" }}
							{{ result.import_type === UPDATE ? "updated" : "added" }}<template v-if="result.failed.length">, <b>{{ failedCount }}</b> not saved</template>.</p>
					</div>
					<div v-if="result.failed.length" class="rounded-lg border bg-white">
						<h3 class="border-b px-4 py-3 font-semibold">Rows not saved, and why</h3>
						<ul class="divide-y text-sm"><li v-for="(f, i) in result.failed" :key="i" class="px-4 py-2.5"><b>Row {{ f.rows.join(", ") }}:</b> {{ f.reason }}</li></ul>
						<div class="flex flex-wrap gap-2 border-t p-3">
							<Button icon-left="download" label="Download these rows" @click="downloadFailed" />
							<Button variant="solid" icon-left="refresh-cw" label="Fix them and import again" @click="again" />
						</div>
						<p class="border-t px-4 py-2 text-xs text-gray-500">The download holds only the rows that weren't saved, with the same columns. Correct them and upload that file: rows already saved aren't imported twice.</p>
					</div>
					<div class="flex flex-wrap gap-2">
						<a :href="result.list_url" target="_blank" class="inline-flex"><Button icon-right="external-link" :label="`See ${result.doctype} in desk`" /></a>
						<Button label="Import something else" @click="startOver" />
					</div>
				</template>
			</section>
		</div>

		<div v-if="step === 4 && check" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-[1200px] flex-wrap items-center gap-3">
				<div class="min-w-0 flex-1 text-sm">
					<template v-if="check.ready"><b>{{ toImport }}</b> {{ check.doctype }} record{{ toImport === 1 ? "" : "s" }} will be {{ check.import_type === UPDATE ? "updated" : "added" }}.</template>
					<span v-else class="text-amber-800">Sort out the items above to import.</span>
				</div>
				<Button label="Upload a corrected file" @click="step = 3" />
				<Button variant="solid" label="Import" :disabled="!check.ready || saving" @click="confirmOpen = true" />
			</div>
		</div>

		<Dialog v-model="confirmOpen" :options="{ title: `Import ${toImport} ${check?.doctype} record${toImport === 1 ? '' : 's'}?`, size: 'md' }">
			<template #body-content>
				<div class="space-y-2 text-sm">
					<p v-if="check?.import_type === UPDATE">{{ toImport }} existing record{{ toImport === 1 ? "" : "s" }} change, using the columns in <b>{{ check?.filename }}</b>. Columns not in the file stay as they are.</p>
					<p v-else>{{ toImport }} new record{{ toImport === 1 ? " is" : "s are" }} added from <b>{{ check?.filename }}</b>.</p>
					<p v-if="submitAfter" class="text-amber-800">Each one is submitted as well.</p>
					<p class="text-gray-600">No emails are sent while importing. There is no undo button: each record is saved under your name and can be changed or deleted in desk like any other.</p>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Import" :loading="running" @click="run" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Dialog, FeatherIcon, LoadingIndicator } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import LinkField from "@/components/LinkField.vue"
import Steps from "../components/Steps.vue"
import RecordTypePicker from "../components/RecordTypePicker.vue"
import { adm, download, fail, ok } from "../api"

const STEPS = ["What", "New or update", "Your file", "Upload", "Check", "Import"]
const INSERT = "Insert New Records"
const UPDATE = "Update Existing Records"
const DONT = "Don't Import"
const MODES = [
	{ value: INSERT, icon: "plus-circle", title: "Add new records", text: (t) => `Every row becomes a new ${t.doctype}.` },
	{ value: UPDATE, icon: "edit-3", title: "Update existing records", text: (t) => `Every row changes a ${t.doctype} that's already in the system, found by its ${t.id_label}.` },
]

const props = defineProps({ name: String })
const route = useRoute()
const router = useRouter()

const step = ref(0)
const doctype = ref(route.query.type || "")
const type = ref(null)
const mode = ref("")
const submitAfter = ref(false)
const check = ref(null)
const result = ref(null)
const reading = ref(false)
const dragging = ref(false)
const saving = ref(false)
const running = ref(false)
const confirmOpen = ref(false)
let poll = null
let ran = false  // toast the finish only for an import started on this visit

async function loadType(dt) {
	type.value = await adm("get_data_type", { doctype: dt })
}

async function pick(dt) {
	doctype.value = dt
	try {
		await loadType(dt)
		mode.value = mode.value || INSERT
		step.value = 1
	} catch (e) {
		fail(e)
	}
}

function go(i) {
	step.value = i
}

// An import opened by its name: back to its check while it hasn't run, else its result
async function open(name) {
	try {
		const c = await adm("get_import_check", { name })
		doctype.value = c.doctype
		mode.value = c.import_type
		await loadType(c.doctype)
		if (c.status === "Pending") {
			check.value = c
			step.value = 4
		} else {
			step.value = 5
			await refresh()
		}
	} catch (e) {
		fail(e, "Could not open that import")
	}
}
if (props.name) open(props.name)
else if (doctype.value) pick(doctype.value)

watch(() => props.name, (n, before) => n && n !== check.value?.name && n !== before && open(n))

function template() {
	download("export_data", { doctype: doctype.value, template: 1, fmt: "Excel", with_id: mode.value === UPDATE ? 1 : 0 })
}

function exportExisting() {
	download("export_data", { doctype: doctype.value, fmt: "Excel", with_id: 1 })
}

function drop(e) {
	dragging.value = false
	upload(e.dataTransfer.files[0])
}

async function upload(file, ev) {
	if (ev) ev.target.value = ""
	if (!file) return
	if (!/\.(csv|xlsx)$/i.test(file.name)) return fail({ message: "Upload a CSV or Excel (.xlsx) file." }, "Not a file the import reads")
	reading.value = true
	try {
		const content = await new Promise((resolve, reject) => {
			const r = new FileReader()
			r.onload = () => resolve(String(r.result).split(",")[1])
			r.onerror = reject
			r.readAsDataURL(file)
		})
		// a corrected file replaces the one on an import that hasn't run; otherwise it is a new import
		check.value = check.value && check.value.status === "Pending" && check.value.doctype === doctype.value && check.value.import_type === mode.value
			? await adm("replace_import_file", { name: check.value.name, filename: file.name, content })
			: await adm("create_import", { doctype: doctype.value, import_type: mode.value, filename: file.name, content, submit_after_import: submitAfter.value ? 1 : 0 })
		result.value = null
		step.value = 4
		router.replace({ path: `/data/import/${encodeURIComponent(check.value.name)}` })
	} catch (e) {
		fail(e, "Could not read the file")
	} finally {
		reading.value = false
	}
}

const todo = computed(() => (check.value ? check.value.must_fix.length + check.value.values.filter((v) => !v.target && !isLeftOut(v)).length : 0))
const toImport = computed(() => check.value?.records || 0)
const fieldGroups = computed(() => {
	if (!type.value) return []
	const [main, ...tables] = type.value.tables
	const id = { key: "name", label: "ID", required: false }
	return [
		{ label: main.label, fields: [...(type.value.id_field === "name" ? [id] : []), ...main.columns] },
		...tables.map((t) => ({ label: `${t.label} (table)`, fields: [{ key: `${t.key}.name`, label: `ID (${t.label})` }, ...t.columns] })),
	]
})

const isLeftOut = (v) => v.rows.every((r) => check.value.skipped_rows.includes(r))
const firstValue = (i) => check.value.sample.map((r) => r[i]).find((v) => v !== null && v !== undefined && v !== "") ?? ""

async function save(params) {
	saving.value = true
	try {
		check.value = await adm("save_import_choices", { name: check.value.name, ...params })
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

function setColumn(c, key) {
	const columns = Object.fromEntries(check.value.columns.map((x) => [x.index, x.key || DONT]))
	columns[c.index] = key
	save({ columns })
}

function setValue(v, target) {
	save({ values: { [v.id]: target || "" } })
}

function toggleRow(...rows) {
	const skipped = new Set(check.value.skipped_rows)
	const allOut = rows.every((r) => skipped.has(r))
	rows.forEach((r) => (allOut ? skipped.delete(r) : skipped.add(r)))
	save({ skip_rows: [...skipped] })
}

async function run() {
	running.value = true
	try {
		result.value = await adm("run_import", { name: check.value.name })
		ran = true
		confirmOpen.value = false
		step.value = 5
		watchProgress()
	} catch (e) {
		fail(e, "Import not started")
	} finally {
		running.value = false
	}
}

const inFlight = computed(() => result.value && ["Pending", "In Progress"].includes(result.value.status) && !result.value.blocked.length)
const failedCount = computed(() => (result.value?.failed || []).reduce((n, f) => n + Math.max(f.rows.length, 1), 0))
const headline = computed(() => {
	const r = result.value
	if (!r.failed.length) return "All done"
	return r.succeeded ? "Partly done" : "Nothing was saved"
})

async function refresh() {
	try {
		result.value = await adm("get_import_result", { name: props.name || check.value.name })
	} catch (e) {
		fail(e)
	}
	watchProgress()
}

function watchProgress() {
	clearTimeout(poll)
	if (inFlight.value) poll = setTimeout(refresh, 2000)
	else if (ran && result.value && !result.value.blocked.length && !result.value.failed.length) {
		ran = false
		ok("Import finished", `${result.value.succeeded} ${result.value.doctype} saved`)
	}
}
onBeforeUnmount(() => clearTimeout(poll))

function downloadFailed() {
	window.open(`/api/method/frappe.core.doctype.data_import.data_import.download_errored_template?data_import_name=${encodeURIComponent(result.value.name)}`, "_blank")
}

async function reopenCheck() {
	check.value = await adm("get_import_check", { name: result.value.name })
	step.value = 4
}

function again() {
	check.value = null
	result.value = null
	step.value = 3
	router.replace({ path: "/data/import", query: { type: doctype.value } })
}

function startOver() {
	check.value = null
	result.value = null
	type.value = null
	doctype.value = ""
	mode.value = ""
	step.value = 0
	router.replace({ path: "/data/import" })
}
</script>
