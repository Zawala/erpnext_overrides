<template>
	<div class="flex h-full min-h-0 flex-col">
		<PageHeader :title="heading" :subtitle="isNew ? `New ${cfg.doctype}` : `${cfg.doctype} · ${name}`" :back="`/records/${slug}`">
			<template #badge><StatusBadge v-if="doc" :status="statusLabel" /></template>
			<div v-if="doc" class="hidden md:flex items-center gap-2">
				<Button v-if="canPrint" icon-left="printer" label="Print" @click="printOpen = true" />
				<Button v-if="!isNew" :link="deskUrl(cfg.doctype, name)" icon-left="external-link" label="Desk" variant="ghost" />
				<Button v-for="a in actions" :key="a.label" :icon-left="a.icon" :label="a.label" :loading="busy === a.label" @click="runAction(a)" />
				<Button v-if="canCancel" theme="red" variant="subtle" label="Cancel" @click="cancelOpen = true" />
				<Button v-if="primary" variant="solid" :label="primary.label" :loading="busy === 'primary'" @click="primary.action" />
			</div>
		</PageHeader>

		<div v-if="!doc" class="flex flex-1 items-center justify-center text-gray-500">
			<p v-if="errors.length" class="text-red-700">{{ errors.join(" ") }}</p>
			<LoadingIndicator v-else class="h-5 w-5" />
		</div>
		<div v-else class="flex-1 overflow-y-auto">
			<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4 pb-28 md:pb-6">
				<div v-if="fromAction" class="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
					<FeatherIcon name="git-branch" class="h-4 w-4" /> {{ fromAction }} Check it, then save.
				</div>
				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 p-4">
					<div class="flex items-start gap-3">
						<FeatherIcon name="x-octagon" class="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
						<div class="flex-1 space-y-1 text-sm text-red-800"><p v-for="m in errors" :key="m">{{ m }}</p></div>
						<button class="text-red-400 hover:text-red-700" aria-label="Dismiss" @click="errors = []"><FeatherIcon name="x" class="h-4 w-4" /></button>
					</div>
				</div>

				<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4 items-start">
					<div class="space-y-4 min-w-0">
						<section v-for="s in cfg.sections" :key="s.label" class="rounded-lg border bg-white">
							<h3 class="border-b px-4 py-3 text-base font-semibold">{{ s.label }}</h3>
							<div class="grid grid-cols-1 gap-x-6 gap-y-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
								<Field v-for="f in s.fields" :key="f.fieldname" :field="f" :doc="doc" :readonly="readonly" @change="setField" />
							</div>
						</section>
						<ItemsTable v-if="cfg.items" :doc="doc" :config="cfg.items" :readonly="readonly" @changed="dirty = true" />
						<ChildTable v-for="t in cfg.tables || []" :key="t.field" :doc="doc" :config="t" :readonly="readonly" @changed="dirty = true">
							<template v-if="t.fetch && !readonly && t.fetch.show(doc)" #actions>
								<Button :label="t.fetch.label" icon-left="download" :loading="busy === t.field" @click="runFetch(t)" />
							</template>
						</ChildTable>
					</div>

					<aside class="space-y-4 xl:sticky xl:top-4">
						<!-- three-way match: a supplier's bill from a purchase order (erp_overrides.three_way) -->
						<section v-if="match" class="rounded-lg border bg-white p-4">
							<div class="flex items-center justify-between gap-2">
								<h3 class="text-base font-semibold">Order · receipt · bill</h3>
								<span class="rounded px-1.5 py-0.5 text-xs" :class="MATCH_THEME[match.status]">{{ match.label }}</span>
							</div>
							<p class="mt-2 text-sm" :class="match.payable ? 'text-gray-600' : 'text-amber-800'">{{ match.message }}</p>
							<dl v-if="match.lines.length" class="mt-3 space-y-2 text-xs tabular">
								<div v-for="l in match.lines" :key="l.po_detail" class="rounded border px-2 py-1.5">
									<div class="font-medium">{{ l.item_code }} <span class="font-normal text-gray-500">· {{ l.purchase_order }}</span></div>
									<div class="text-gray-600">Billed {{ l.billed }} of {{ l.received }} received · rate {{ l.rate }} (ordered {{ l.ordered_rate }})</div>
								</div>
							</dl>
							<p v-if="!match.payable" class="mt-2 text-xs text-gray-500">It can't be paid until the rest is received or the bill is corrected. An Accounts Manager can approve paying it anyway, on the payment.</p>
						</section>
						<section v-if="cfg.summary" class="rounded-lg border bg-white p-4">
							<h3 class="text-base font-semibold">Totals</h3>
							<dl class="mt-3 space-y-2 text-sm tabular">
								<div v-for="r in cfg.summary(doc)" :key="r.label" class="flex justify-between gap-3"
									:class="r.strong ? 'border-t pt-2 text-base font-medium' : ''">
									<dt :class="r.strong ? '' : 'text-gray-500'">{{ r.label }}</dt>
									<dd :class="r.warn ? 'text-amber-700' : ''">{{ r.value }}</dd>
								</div>
							</dl>
							<p v-if="(dirty || isNew) && (cfg.items || cfg.doctype === 'Payment Entry')" class="mt-3 text-xs text-gray-500">
								Totals are worked out by the server — save to update them.
							</p>
						</section>
						<section v-if="!isNew" class="rounded-lg border bg-white p-4 text-xs text-gray-500 space-y-1">
							<div>Created by {{ doc.owner }}</div>
							<div>Last changed {{ relative(doc.modified) }} by {{ doc.modified_by }}</div>
						</section>
					</aside>
				</div>
			</div>
		</div>

		<!-- Mobile action bar -->
		<div v-if="doc && (primary || actions.length || canPrint)"
			class="md:hidden fixed inset-x-0 bottom-[calc(56px+env(safe-area-inset-bottom))] z-20 flex gap-2 border-t bg-white p-3">
			<Button v-if="canPrint" icon="printer" size="lg" @click="printOpen = true" />
			<Button v-for="a in actions" :key="a.label" size="lg" :label="a.label" :loading="busy === a.label" @click="runAction(a)" />
			<Button v-if="primary" variant="solid" size="lg" class="flex-1" :label="primary.label" :loading="busy === 'primary'" @click="primary.action" />
		</div>

		<PrintPreview v-if="canPrint" v-model:open="printOpen" :doctype="cfg.doctype" :name="name" />

		<Dialog v-model="cancelOpen" :options="{ title: `Cancel ${name}?`, size: 'sm' }">
			<template #body-content>
				<p class="text-sm text-gray-700">This reverses its ledger entries. A cancelled {{ cfg.doctype.toLowerCase() }} can't be edited; amend it in desk to make a corrected copy.</p>
				<div class="mt-4 flex justify-end gap-2">
					<Button label="Keep it" @click="cancelOpen = false" />
					<Button theme="red" variant="solid" label="Cancel it" :loading="busy === 'cancel'" @click="cancelDoc" />
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"
import { Dialog, FeatherIcon, LoadingIndicator, call, toast } from "frappe-ui"
import Field from "@/components/Field.vue"
import ItemsTable from "@/components/ItemsTable.vue"
import ChildTable from "@/components/ChildTable.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import PrintPreview from "@/components/PrintPreview.vue"
import PageHeader from "@/hr/components/PageHeader.vue"
import { relative } from "@/utils/format"
import { bumpList } from "@/data/lists"
import { records, pendingRecords, MATCH_THEME } from "../records"
import { deskUrl, errorMessages, ok } from "../api"

const props = defineProps({ slug: String, name: String })
const router = useRouter()

const cfg = computed(() => records[props.slug])
const isNew = computed(() => !props.name)
const doc = ref(null)
const dirty = ref(false)
const busy = ref("")
const errors = ref([])
const fromAction = ref("")
const printOpen = ref(false)
const cancelOpen = ref(false)

const readonly = computed(() => !!doc.value && doc.value.docstatus !== 0)
const heading = computed(() => (doc.value && cfg.value.title(doc.value)) || props.name)
const statusLabel = computed(() => (isNew.value || dirty.value ? "Not saved" : cfg.value.status(doc.value)))
const canPrint = computed(() => cfg.value.printable && !isNew.value && doc.value?.docstatus === 1)
const canCancel = computed(() => cfg.value.submittable && !isNew.value && doc.value?.docstatus === 1)
const actions = computed(() => (doc.value && !isNew.value && !dirty.value && cfg.value.actions ? cfg.value.actions(doc.value) : []))

const primary = computed(() => {
	const d = doc.value
	if (!d || d.docstatus !== 0) return null
	if (isNew.value || dirty.value) return { label: "Save", action: save }
	if (!cfg.value.submittable) return null
	return { label: "Submit", action: submit }
})

const match = ref(null)

async function load() {
	errors.value = []
	match.value = null
	dirty.value = false
	fromAction.value = ""
	if (isNew.value) {
		const pending = pendingRecords.get(props.slug)
		pendingRecords.delete(props.slug)
		doc.value = { doctype: cfg.value.doctype, docstatus: 0, ...(pending?.doc || cfg.value.defaults()) }
		if (pending) {
			dirty.value = true
			fromAction.value = pending.note
		}
		return
	}
	try {
		doc.value = await call("frappe.client.get", { doctype: cfg.value.doctype, name: props.name })
		match.value = cfg.value.doctype === "Purchase Invoice"
			? await call("erp_overrides.api.accounts.get_match", { invoice: props.name }).catch(() => null) : null
	} catch (e) {
		errors.value = errorMessages(e)
		doc.value = null
	}
}
watch(() => [props.slug, props.name], load, { immediate: true })

async function setField(fieldname, value) {
	const d = doc.value
	d[fieldname] = value
	// otherwise ERPNext resets posting_date to "now" on save
	if (fieldname === "posting_date") d.set_posting_time = 1
	dirty.value = true
	const hook = cfg.value.onChange?.[fieldname]
	if (!hook) return
	try {
		await hook(d)
	} catch (e) {
		errors.value = errorMessages(e)
	}
}

async function runFetch(table) {
	busy.value = table.field
	errors.value = []
	try {
		const note = await table.fetch.run(doc.value)
		dirty.value = true
		if (note) toast({ title: table.fetch.label, text: note, icon: "check", iconClasses: "text-green-600" })
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = ""
	}
}

async function runAction(a) {
	busy.value = a.label
	errors.value = []
	try {
		const { slug, doc: made } = await a.run(doc.value)
		pendingRecords.set(slug, { doc: made, note: `Made from ${cfg.value.doctype} ${props.name}.` })
		router.push(`/records/${slug}/new`)
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = ""
	}
}

/** The doc as the server wants it: no UI keys, and a mapped new doc loses its placeholder names. */
function cleanDoc() {
	const d = JSON.parse(JSON.stringify(doc.value))
	const fresh = isNew.value
	if (fresh) for (const k of ["name", "__islocal", "__unsaved", "owner", "creation", "modified"]) delete d[k]
	for (const value of Object.values(d)) {
		if (!Array.isArray(value)) continue
		for (const row of value) {
			if (!row || typeof row !== "object") continue
			delete row._key
			if (fresh) for (const k of ["name", "parent", "__islocal", "__unsaved"]) delete row[k]
		}
	}
	return d
}

async function save() {
	busy.value = "primary"
	errors.value = []
	try {
		const saved = await call(isNew.value ? "frappe.client.insert" : "frappe.client.save", { doc: cleanDoc() })
		doc.value = saved
		dirty.value = false
		fromAction.value = ""
		bumpList(cfg.value.doctype)
		ok("Saved", saved.name)
		if (isNew.value) router.replace(`/records/${props.slug}/${encodeURIComponent(saved.name)}`)
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = ""
	}
}

async function submit() {
	busy.value = "primary"
	errors.value = []
	try {
		doc.value = await call("frappe.client.submit", { doc: cleanDoc() })
		bumpList(cfg.value.doctype)
		ok("Submitted", doc.value.name)
		await load()
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = ""
	}
}

async function cancelDoc() {
	busy.value = "cancel"
	errors.value = []
	try {
		await call("frappe.client.cancel", { doctype: cfg.value.doctype, name: props.name })
		bumpList(cfg.value.doctype)
		ok("Cancelled", props.name)
		cancelOpen.value = false
		await load()
	} catch (e) {
		cancelOpen.value = false
		errors.value = errorMessages(e)
	} finally {
		busy.value = ""
	}
}

const confirmLeave = () => !dirty.value || window.confirm("You have unsaved changes. Leave without saving?")
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => (to.params.name === from.params.name ? true : confirmLeave()))
</script>
