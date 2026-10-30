<template>
	<div class="flex h-full min-h-0 flex-col">
		<PageHeader :title="`${cfg.title} · ${doc?.employee_name || employee}`" :subtitle="cfg.subtitle" :back="`/people/${employee}`">
			<Button label="Save draft" :loading="busy === 'save'" :disabled="!doc || !!busy" @click="save(false)" />
			<Button variant="solid" :label="`Submit ${cfg.title.toLowerCase()}`" :loading="busy === 'submit'" :disabled="!doc || !!busy" @click="save(true)" />
		</PageHeader>

		<div v-if="!doc" class="flex flex-1 items-center justify-center"><LoadingIndicator class="h-5 w-5 text-gray-500" /></div>
		<div v-else class="flex-1 overflow-y-auto">
			<div class="mx-auto w-full max-w-[1200px] p-4 lg:p-6 space-y-4 pb-28 md:pb-6">
				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 space-y-1">
					<p v-for="m in errors" :key="m">{{ m }}</p>
				</div>

				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Details</h3>
					<div class="grid grid-cols-1 gap-x-6 gap-y-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
						<Field v-for="f in cfg.fields" :key="f.fieldname" :field="f" :doc="doc" @change="(k, v) => (doc[k] = v)" />
					</div>
				</section>

				<!-- What changes (promotion / transfer) -->
				<section v-if="cfg.table" class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<div>
							<h3 class="font-semibold">What changes</h3>
							<p class="text-xs text-gray-500">Applied to the employee record on submit. The old value stays here as history.</p>
						</div>
						<select class="form-select w-56" :value="''" aria-label="Add a change" @change="addRow($event.target.value); $event.target.value = ''">
							<option value="" disabled>+ Add a change</option>
							<option v-for="p in available" :key="p.fieldname" :value="p.fieldname">{{ p.label }}</option>
						</select>
					</header>
					<ul class="divide-y">
						<li v-for="(r, i) in doc[cfg.table]" :key="r.fieldname" class="grid grid-cols-1 items-center gap-3 px-4 py-3 sm:grid-cols-[180px_1fr_1fr_auto]">
							<div class="font-medium">{{ r.property }}</div>
							<div class="text-sm text-gray-500">Now: {{ r.current || "—" }}</div>
							<div>
								<LinkField v-if="prop(r).fieldtype === 'Link'" :doctype="prop(r).options" :model-value="r.new" @update:model-value="(v) => (r.new = v)" />
								<select v-else-if="prop(r).fieldtype === 'Select'" v-model="r.new" class="form-select w-full">
									<option v-for="o in (prop(r).options || '').split('\n')" :key="o" :value="o">{{ o }}</option>
								</select>
								<input v-else v-model="r.new" class="form-input w-full" />
							</div>
							<button class="justify-self-end rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-red-600" title="Remove" aria-label="Remove change"
								@click="doc[cfg.table].splice(i, 1)"><FeatherIcon name="trash-2" class="h-4 w-4" /></button>
						</li>
						<li v-if="!doc[cfg.table].length" class="px-4 py-8 text-center text-sm text-gray-500">
							Add what changes — designation, grade, department, reports to…
						</li>
					</ul>
				</section>

				<!-- Exit checklist (separation) -->
				<section v-if="kind === 'separation'" class="rounded-lg border bg-white">
					<header class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
						<div>
							<h3 class="font-semibold">Exit checklist</h3>
							<p class="text-xs text-gray-500">Return laptop, revoke access, final leave encashment, handover — each with an owner.</p>
						</div>
						<div class="flex gap-2">
							<div class="w-56"><LinkField :model-value="doc.employee_separation_template" doctype="Employee Separation Template"
								placeholder="Load a template" @update:model-value="loadTemplate" /></div>
							<Button icon-left="plus" label="Activity" @click="doc.activities.push({ activity_name: '', user: '', begin_on: 0, duration: 1 })" />
						</div>
					</header>
					<ul class="divide-y">
						<li v-for="(a, i) in doc.activities" :key="i" class="grid grid-cols-1 items-center gap-3 px-4 py-3 sm:grid-cols-[1fr_220px_90px_90px_auto]">
							<input v-model="a.activity_name" class="form-input w-full" placeholder="Activity" aria-label="Activity" />
							<LinkField :model-value="a.user" doctype="User" placeholder="Owner" @update:model-value="(v) => (a.user = v)" />
							<label class="text-xs text-gray-500">Starts day<input v-model.number="a.begin_on" type="number" min="0" class="form-input w-full" /></label>
							<label class="text-xs text-gray-500">Days<input v-model.number="a.duration" type="number" min="0" class="form-input w-full" /></label>
							<button class="justify-self-end rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-red-600" title="Remove" aria-label="Remove activity"
								@click="doc.activities.splice(i, 1)"><FeatherIcon name="trash-2" class="h-4 w-4" /></button>
						</li>
						<li v-if="!doc.activities.length" class="px-4 py-8 text-center text-sm text-gray-500">No activities yet — load a template or add them.</li>
					</ul>
					<div class="space-y-3 border-t p-4">
						<label class="flex items-center gap-2 text-sm"><input v-model="doc.notify_users_by_email" type="checkbox" class="form-checkbox" :true-value="1" :false-value="0" />
							Email each owner when the exit starts</label>
						<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Exit interview</span>
							<textarea v-model="doc.exit_interview" rows="4" class="form-textarea w-full" /></label>
					</div>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { LoadingIndicator, call } from "frappe-ui"
import Field from "@/components/Field.vue"
import LinkField from "@/components/LinkField.vue"
import { hr, ok, errorMessages } from "../api"
import PageHeader from "../components/PageHeader.vue"

const props = defineProps({ employee: String, kind: String })
const router = useRouter()

const CONFIG = {
	promotion: {
		doctype: "Employee Promotion", slug: "promotions", title: "Promotion", table: "promotion_details",
		subtitle: "Pick the date, then list what changes — designation, grade, department, CTC",
		fields: [
			{ fieldname: "promotion_date", label: "Promotion date", type: "Date", reqd: true, help: "It can only be submitted on or after this date." },
			{ fieldname: "current_ctc", label: "Current CTC", type: "Currency" },
			{ fieldname: "revised_ctc", label: "Revised CTC", type: "Currency" },
		],
	},
	transfer: {
		doctype: "Employee Transfer", slug: "transfers", title: "Transfer", table: "transfer_details",
		subtitle: "A move between departments, branches or companies",
		fields: [
			{ fieldname: "transfer_date", label: "Transfer date", type: "Date", reqd: true },
			{ fieldname: "new_company", label: "New company", type: "Link", options: "Company", help: "Only for a move to another company." },
		],
	},
	separation: {
		doctype: "Employee Separation", slug: "separations", title: "Exit",
		subtitle: "Resignation date, last working day and the checklist that cannot be skipped",
		fields: [
			{ fieldname: "resignation_letter_date", label: "Resignation letter date", type: "Date" },
			{ fieldname: "boarding_begins_on", label: "Separation begins on", type: "Date", reqd: true },
		],
	},
}

const cfg = computed(() => CONFIG[props.kind] || CONFIG.promotion)
const doc = ref(null)
const props_ = ref([])
const errors = ref([])
const busy = ref(null)

const available = computed(() => props_.value.filter((p) => !(doc.value?.[cfg.value.table] || []).some((r) => r.fieldname === p.fieldname)))
const prop = (row) => props_.value.find((p) => p.fieldname === row.fieldname) || {}

function addRow(fieldname) {
	const p = props_.value.find((x) => x.fieldname === fieldname)
	if (p) doc.value[cfg.value.table].push({ fieldname, property: p.label, current: p.current ?? "", new: "" })
}

async function loadTemplate(template) {
	doc.value.employee_separation_template = template
	if (!template) return
	const rows = await hr("get_separation_activities", { template })
	doc.value.activities = rows.map((r) => ({ ...r }))
}

async function load() {
	errors.value = []
	doc.value = null
	const [d, p] = await Promise.all([
		hr("new_lifecycle_doc", { employee: props.employee, doctype: cfg.value.doctype }),
		cfg.value.table ? hr("get_property_fields", { employee: props.employee }) : Promise.resolve([]),
	])
	props_.value = p
	doc.value = d
}

async function save(submit) {
	busy.value = submit ? "submit" : "save"
	errors.value = []
	try {
		const table = cfg.value.table
		if (table && doc.value[table].some((r) => !r.new)) throw { messages: ["Every change needs a new value."] }
		if (table && !doc.value[table].length) throw { messages: ["Add at least one change."] }
		// keep the saved doc, so a failed submit is retried on the same draft rather than a new one
		doc.value = await call(doc.value.name ? "frappe.client.save" : "frappe.client.insert", { doc: doc.value })
		let saved = doc.value
		if (submit) saved = await call("frappe.client.submit", { doc: doc.value })
		ok(submit ? `${cfg.value.title} submitted` : "Draft saved", saved.name)
		router.replace(`/records/${cfg.value.slug}/${encodeURIComponent(saved.name)}`)
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = null
	}
}

watch(() => [props.employee, props.kind], load, { immediate: true })
</script>
