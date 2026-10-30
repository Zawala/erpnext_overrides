<template>
	<div class="flex h-full min-h-0 flex-col">
		<PageHeader :title="doc ? cfg.title(doc) : name" :subtitle="`${cfg.doctype} · ${name}`" :back="`/records/${slug}`">
			<template #badge><StatusBadge v-if="doc" :status="cfg.status(doc)" /></template>
			<Button v-if="doc && cfg.printable" icon-left="printer" label="Print" @click="printOpen = true" />
			<Button :link="deskUrl(cfg.doctype, name)" icon-left="external-link" label="Desk" variant="ghost" />
			<Button v-if="canSubmit" variant="solid" :label="`Submit`" :loading="busy" @click="submit" />
		</PageHeader>

		<div v-if="!doc" class="flex flex-1 items-center justify-center text-gray-500">
			<p v-if="errors.length" class="text-red-700">{{ errors.join(" ") }}</p>
			<LoadingIndicator v-else class="h-5 w-5" />
		</div>
		<div v-else class="flex-1 overflow-y-auto">
			<div class="mx-auto w-full max-w-[1400px] p-4 lg:p-6 space-y-4">
				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 space-y-1">
					<p v-for="m in errors" :key="m">{{ m }}</p>
				</div>
				<p v-if="canSubmit && cfg.submitHint" class="text-sm text-gray-500">{{ cfg.submitHint }}</p>

				<section v-for="s in cfg.sections" :key="s.label" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">{{ s.label }}</h3>
					<dl class="grid grid-cols-1 gap-x-6 gap-y-3 p-4 text-sm sm:grid-cols-2 xl:grid-cols-4">
						<div v-for="[field, label, format] in s.fields" :key="field" :class="format === 'text' ? 'sm:col-span-2 xl:col-span-4' : ''">
							<dt class="text-gray-500">{{ label }}</dt>
							<dd class="font-medium whitespace-pre-line break-words">{{ show(doc[field], format) }}</dd>
						</div>
					</dl>
				</section>

				<section v-for="t in tables" :key="t.field" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">{{ t.label }}</h3>
					<div class="overflow-x-auto">
						<table class="w-full text-sm tabular">
							<thead class="bg-gray-50">
								<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
									<th v-for="[f, label, format] in t.columns" :key="f" class="px-4 py-2 font-medium" :class="format === 'money' ? 'text-right' : ''">{{ label }}</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="row in doc[t.field]" :key="row.name" class="border-t align-top">
									<td v-for="[f, , format] in t.columns" :key="f" class="px-4 py-2" :class="format === 'money' ? 'text-right' : ''">{{ show(row[f], format) }}</td>
								</tr>
								<tr v-if="!doc[t.field]?.length"><td :colspan="t.columns.length" class="px-4 py-6 text-center text-gray-500">None.</td></tr>
							</tbody>
						</table>
					</div>
				</section>

				<section v-if="cfg.attachments" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Attachments</h3>
					<div class="flex flex-wrap gap-2 p-4">
						<a v-for="f in files" :key="f.file_url" :href="f.file_url" target="_blank"
							class="flex items-center gap-1.5 rounded border px-2 py-1 text-sm text-gray-700 hover:bg-gray-50">
							<FeatherIcon name="paperclip" class="h-4 w-4" /><span class="max-w-[14rem] truncate">{{ f.file_name }}</span>
						</a>
						<span v-if="!files.length" class="text-sm text-gray-500">No attachments.</span>
					</div>
				</section>

				<p class="text-xs text-gray-400">Created by {{ doc.owner }} · last changed {{ relative(doc.modified) }} by {{ doc.modified_by }}</p>
			</div>
		</div>

		<PrintPreview v-if="cfg.printable" v-model:open="printOpen" :doctype="cfg.doctype" :name="name"
			v-bind="cfg.doctype === 'Salary Slip' ? payslipPrint() : {}" />
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"
import PrintPreview from "@/components/PrintPreview.vue"
import { money, date, relative } from "@/utils/format"
import { ok, errorMessages, deskUrl, can, payslipPrint } from "../api"
import { records } from "../records"
import PageHeader from "../components/PageHeader.vue"

const props = defineProps({ slug: String, name: String })
const cfg = computed(() => records[props.slug] || records["leave-applications"])
const doc = ref(null)
const files = ref([])
const errors = ref([])
const busy = ref(false)
const printOpen = ref(false)

const tables = computed(() => cfg.value.tables || (cfg.value.table ? [cfg.value.table] : []))
// lifecycle drafts can be submitted here; requests are decided in the Inbox, payroll in its run
const canSubmit = computed(() => doc.value?.docstatus === 0 && ["promotions", "transfers", "separations"].includes(props.slug) && can(cfg.value.doctype, "create"))

const strip = (s) => String(s ?? "").replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "").trim()
function show(v, format) {
	if (v === null || v === undefined || v === "") return "—"
	if (format === "date") return date(v)
	if (format === "money") return money(v, doc.value.currency || doc.value.salary_currency)
	if (format === "days") return Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })
	if (format === "check") return v ? "Yes" : "No"
	if (format === "text") return strip(v) || "—"
	return v
}

async function load() {
	errors.value = []
	try {
		doc.value = await call("frappe.client.get", { doctype: cfg.value.doctype, name: props.name })
		if (cfg.value.attachments) {
			files.value = await call("frappe.client.get_list", {
				doctype: "File", fields: ["file_name", "file_url"],
				filters: { attached_to_doctype: cfg.value.doctype, attached_to_name: props.name },
			})
		}
	} catch (e) {
		errors.value = errorMessages(e)
	}
}

async function submit() {
	busy.value = true
	errors.value = []
	try {
		doc.value = await call("frappe.client.submit", { doc: doc.value })
		ok("Submitted", props.name)
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = false
	}
}

watch(() => [props.slug, props.name], load, { immediate: true })
</script>
