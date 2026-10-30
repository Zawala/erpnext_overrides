<template>
	<div class="flex h-full min-h-0 flex-col bg-gray-50">
		<!-- Header -->
		<header class="sticky top-0 z-20 flex items-center gap-3 border-b bg-white px-4 lg:px-6 h-14 shrink-0">
			<router-link :to="`/${cfg.slug}`" class="min-[1600px]:hidden -ml-1 rounded p-1 text-gray-600 hover:bg-gray-100" aria-label="Back">
				<FeatherIcon name="chevron-left" class="h-5 w-5" />
			</router-link>
			<div class="min-w-0 flex-1">
				<div class="flex items-center gap-2">
					<h1 class="truncate text-lg font-semibold">{{ heading }}</h1>
					<StatusBadge v-if="doc" :status="statusLabel" />
				</div>
				<div class="truncate text-xs text-gray-500">{{ isNew ? `New ${cfg.doctype}` : name }}</div>
			</div>
			<div v-if="doc" class="hidden md:flex items-center gap-2">
				<Button v-if="pdfUrl" icon-left="printer" label="Print" @click="openPrint(false)" />
				<Button v-if="proforma" icon-left="file-text" label="Proforma invoice" @click="openPrint(true)" />
				<Button v-if="!isNew" :link="deskUrl" icon-left="external-link" label="Desk" variant="ghost" />
				<Button v-if="primary" variant="solid" :label="primary.label" :loading="busy" :disabled="primary.disabled"
					@click="primary.action" />
			</div>
		</header>

		<div v-if="!doc" class="flex flex-1 items-center justify-center text-gray-500">
			<LoadingIndicator class="h-5 w-5" />
		</div>

		<div v-else class="flex-1 overflow-y-auto">
			<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4 pb-28 md:pb-6">
				<!-- Chain -->
				<ChainStrip v-if="!isNew" :doctype="cfg.doctype" :name="name" :version="doc.modified" />
				<div v-else-if="fromLabel" class="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
					<FeatherIcon name="git-branch" class="h-4 w-4" />
					Created from {{ fromLabel }} — customer, lines, quantities and rates carried across. Check them, then save.
				</div>

				<!-- Errors, verbatim -->
				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 p-4">
					<div class="flex items-start gap-3">
						<FeatherIcon name="x-octagon" class="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
						<div class="flex-1 space-y-1 text-sm text-red-800">
							<p v-for="m in errors" :key="m">{{ m }}</p>
						</div>
						<button class="text-red-400 hover:text-red-700" @click="errors = []"><FeatherIcon name="x" class="h-4 w-4" /></button>
					</div>
				</div>

				<ApprovalBanner v-if="cfg.approval && !isNew" :doc="doc" :dirty="dirty"
					@status="(s) => (approval = s)" @approved="load" />

				<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4 items-start">
					<!-- Main column -->
					<div class="space-y-4 min-w-0">
						<section v-for="s in cfg.sections" :key="s.label" class="rounded-lg border bg-white">
							<h3 class="border-b px-4 py-3 text-base font-semibold">{{ s.label }}</h3>
							<div class="grid grid-cols-1 gap-x-6 gap-y-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
								<Field v-for="f in s.fields" :key="f.fieldname" :field="f" :doc="doc" :readonly="readonly"
									@change="setField" @quick-create="openQuickCreate" />
							</div>
						</section>

						<ItemsTable v-if="cfg.items" :doc="doc" :config="cfg.items" :readonly="readonly"
							:propagate="cfg.propagate" @changed="dirty = true" />
					</div>

					<!-- Right rail -->
					<aside class="space-y-4 xl:sticky xl:top-4">
						<section v-if="cfg.items" class="rounded-lg border bg-white p-4">
							<h3 class="text-base font-semibold">Totals</h3>
							<dl class="mt-3 space-y-2 text-sm tabular">
								<div class="flex justify-between"><dt class="text-gray-500">Lines</dt><dd>{{ doc.items?.length || 0 }}</dd></div>
								<div class="flex justify-between"><dt class="text-gray-500">Net total</dt><dd>{{ money(netTotal, doc.currency) }}</dd></div>
								<div v-for="t in doc.taxes || []" :key="t.name || t.account_head" class="flex justify-between gap-3">
									<dt class="truncate text-gray-500">{{ t.description || t.account_head }}</dt>
									<dd>{{ dirty || isNew || !t.tax_amount ? (t.rate ? `${t.rate}%` : "—") : money(t.tax_amount, doc.currency) }}</dd>
								</div>
								<div v-if="!doc.taxes?.length && !dirty && doc.total_taxes_and_charges" class="flex justify-between">
									<dt class="text-gray-500">Taxes</dt><dd>{{ money(doc.total_taxes_and_charges, doc.currency) }}</dd>
								</div>
								<div v-if="hasGrandTotal" class="flex justify-between border-t pt-2 text-base">
									<dt class="font-medium">Grand total</dt>
									<dd class="font-semibold">{{ dirty || isNew ? "Save to calculate" : money(doc.grand_total, doc.currency) }}</dd>
								</div>
								<div v-if="doc.doctype === 'Sales Invoice' && doc.docstatus === 1" class="flex justify-between text-base">
									<dt class="font-medium">Outstanding</dt>
									<dd class="font-semibold" :class="doc.outstanding_amount > 0 ? 'text-amber-700' : 'text-green-700'">
										{{ money(doc.outstanding_amount, doc.currency) }}
									</dd>
								</div>
							</dl>
							<p v-if="creditHint" class="mt-3 text-xs text-amber-700">{{ creditHint }}</p>
						</section>

						<NextStep v-if="!isNew && !dirty" :doc="doc" />
						<MarginCard v-if="cfg.margin && !isNew && (doc.docstatus === 1 || cfg.doctype === 'Purchase Order')" :doctype="cfg.doctype" :name="name" :version="doc.modified" />

						<section v-if="!isNew" class="rounded-lg border bg-white p-4 text-xs text-gray-500 space-y-1">
							<div>Created by {{ doc.owner }}</div>
							<div>Last changed {{ relative(doc.modified) }} by {{ doc.modified_by }}</div>
						</section>
					</aside>
				</div>
			</div>
		</div>

		<!-- Mobile action bar -->
		<div v-if="doc && (primary || pdfUrl)" class="md:hidden fixed inset-x-0 bottom-[calc(56px+env(safe-area-inset-bottom))] z-20 border-t bg-white p-3 flex gap-2">
			<Button v-if="pdfUrl" icon="printer" size="lg" label="Print" @click="openPrint(false)" />
			<Button v-if="proforma" icon="file-text" size="lg" label="Proforma invoice" @click="openPrint(true)" />
			<Button v-if="primary" variant="solid" size="lg" class="flex-1" :label="primary.label" :loading="busy"
				:disabled="primary.disabled" @click="primary.action" />
		</div>

		<PrintPreview v-if="doc && !isNew" v-model:open="previewOpen" :doctype="cfg.doctype" :name="name"
			:preset-format="previewProforma ? proforma : undefined" :title="previewProforma ? 'Proforma invoice' : undefined"
			:file-prefix="previewProforma ? 'Proforma-' : ''" />

		<QuickCreate :doctype="quick.doctype" :initial-name="quick.name" @close="quick.doctype = null"
			@created="(n) => setField(quick.fieldname, n)" />
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"
import { FeatherIcon, LoadingIndicator, call, toast } from "frappe-ui"

import Field from "@/components/Field.vue"
import ItemsTable from "@/components/ItemsTable.vue"
import ChainStrip from "@/components/ChainStrip.vue"
import NextStep from "@/components/NextStep.vue"
import ApprovalBanner from "@/components/ApprovalBanner.vue"
import MarginCard from "@/components/MarginCard.vue"
import QuickCreate from "@/components/QuickCreate.vue"
import StatusBadge from "@/components/StatusBadge.vue"

import { bySlug, pendingDocs, docRoute } from "@/doctypes"
import { boot } from "@/boot"
import { errorMessages } from "@/utils/api"
import { money, relative } from "@/utils/format"
import PrintPreview from "@/components/PrintPreview.vue"
import { bumpList } from "@/data/lists"

const props = defineProps({ slug: String, name: String })
const route = useRoute()
const router = useRouter()

const cfg = computed(() => bySlug[props.slug])
const isNew = computed(() => !props.name)
const doc = ref(null)
const dirty = ref(false)
const busy = ref(false)
const errors = ref([])
const approval = ref(null)
const canPrint = ref(false)
const quick = reactive({ doctype: null, name: "", fieldname: null })

const readonly = computed(() => !!doc.value && doc.value.docstatus !== 0)
const heading = computed(() => (doc.value && cfg.value.title(doc.value)) || (isNew.value ? `New ${cfg.value.doctype}` : props.name))
const statusLabel = computed(() => {
	const d = doc.value
	if (isNew.value) return "Not saved"
	if (dirty.value) return "Not saved"
	if (d.docstatus === 2) return "Cancelled"
	if (cfg.value.submittable && d.docstatus === 0) return "Draft"
	return d.status
})
const fromLabel = computed(() => route.query.from?.replace(":", " "))
const netTotal = computed(() => (doc.value?.items || []).reduce((s, r) => s + Number(r.amount || 0), 0))
const hasGrandTotal = computed(() => cfg.value.doctype !== "Opportunity")
const deskUrl = computed(() => `/app/${cfg.value.doctype.toLowerCase().replace(/ /g, "-")}/${props.name}`)

const creditHint = computed(() => {
	const limit = boot.limits?.sales_order_limit
	if (!cfg.value.approval || !limit || !doc.value || doc.value.docstatus !== 0) return ""
	const total = dirty.value || isNew.value ? netTotal.value : doc.value.base_grand_total
	return total > limit ? `Over the ${money(limit)} order limit — a manager must tick Credit Approved before you can submit.` : ""
})

const pdfUrl = computed(() => {
	const d = doc.value
	if (!d || isNew.value || d.docstatus !== 1) return null
	if (!["Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "Purchase Order"].includes(d.doctype)) return null
	if (d.doctype === "Quotation" && !canPrint.value) return null
	return true
})

const previewOpen = ref(false)
const previewProforma = ref(false)
// the proforma format for this doctype, once the document may be printed at all (submitted; approved quotation)
const proforma = computed(() => (pdfUrl.value ? boot.proforma_formats?.[cfg.value.doctype] || null : null))

function openPrint(asProforma) {
	previewProforma.value = asProforma
	previewOpen.value = true
}

const primary = computed(() => {
	const d = doc.value
	if (!d || d.docstatus !== 0) return null
	if (isNew.value || dirty.value) return { label: "Save", action: save }
	if (!cfg.value.submittable) return null
	if (approval.value?.needs_approval) return { label: "Waiting for approval", disabled: true, action: () => {} }
	return { label: `Submit ${cfg.value.doctype}`, action: submit }
})

async function load() {
	errors.value = []
	dirty.value = false
	approval.value = null
	if (isNew.value) {
		const pending = pendingDocs.get(props.slug)
		pendingDocs.delete(props.slug)
		doc.value = { doctype: cfg.value.doctype, docstatus: 0, ...(pending || cfg.value.defaults()) }
		if (pending) dirty.value = true
		return
	}
	try {
		doc.value = await call("frappe.client.get", { doctype: cfg.value.doctype, name: props.name })
	} catch (e) {
		errors.value = errorMessages(e)
		doc.value = null
		return
	}
	if (cfg.value.printable && doc.value.docstatus === 1) {
		canPrint.value = await call("erp_overrides.quotation.can_print", { name: props.name }).catch(() => false)
	}
}

watch(() => [props.slug, props.name], load, { immediate: true })

function setField(fieldname, value) {
	const d = doc.value
	// party_name is a Dynamic Link — a Lead name is meaningless once "Quote to" says Customer
	if (["quotation_to", "opportunity_from"].includes(fieldname) && d[fieldname] !== value) d.party_name = ""
	d[fieldname] = value
	// otherwise ERPNext resets posting_date to "now" on save
	if (fieldname === "posting_date") d.set_posting_time = 1
	const childField = cfg.value.propagate?.[fieldname]
	if (childField) for (const row of d.items || []) row[childField] = value
	dirty.value = true
	const hook = cfg.value.onChange?.[fieldname]
	if (hook) hook(d).catch((e) => (errors.value = errorMessages(e)))
}

function openQuickCreate({ doctype, name, fieldname }) {
	Object.assign(quick, { doctype, name, fieldname })
}

function cleanDoc() {
	const d = JSON.parse(JSON.stringify(doc.value))
	for (const row of d.items || []) delete row._key
	return d
}

async function save() {
	busy.value = true
	errors.value = []
	try {
		const method = isNew.value ? "frappe.client.insert" : "frappe.client.save"
		const saved = await call(method, { doc: cleanDoc() })
		doc.value = saved
		dirty.value = false
		bumpList(cfg.value.doctype)
		toast({ title: "Saved", text: saved.name, icon: "check", iconClasses: "text-green-600" })
		if (isNew.value) router.replace(docRoute(cfg.value.doctype, saved.name))
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = false
	}
}

async function submit() {
	busy.value = true
	errors.value = []
	try {
		doc.value = await call("frappe.client.submit", { doc: cleanDoc() })
		bumpList(cfg.value.doctype)
		toast({ title: "Submitted", text: `${doc.value.name} · ${doc.value.status}`, icon: "check", iconClasses: "text-green-600" })
		await load()
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = false
	}
}

function confirmLeave() {
	return !dirty.value || window.confirm("You have unsaved changes. Leave without saving?")
}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => (to.params.name === from.params.name ? true : confirmLeave()))
</script>
