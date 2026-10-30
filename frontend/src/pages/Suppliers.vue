<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Upload suppliers" subtitle="Add suppliers, or fill in the ones we have, from a spreadsheet. Nothing changes until you apply.">
			<Button icon-left="file" label="Template" @click="template" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] space-y-4 p-4 pb-28 lg:p-6 lg:pb-28">
			<div v-if="gaps?.missing" class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
				<b>{{ gaps.missing }} of {{ gaps.total }} suppliers</b> have no billing currency or payment terms, so they can't be ordered from cleanly:
				{{ gaps.examples.join(", ") }}<template v-if="gaps.missing > gaps.examples.length">, …</template>.
				Put them in the file with both filled in.
			</div>

			<!-- 1. Upload -->
			<section class="rounded-lg border bg-white p-4">
				<div class="flex flex-wrap items-center gap-3">
					<label class="cursor-pointer rounded border border-dashed px-4 py-3 text-sm hover:bg-gray-50">
						<input type="file" accept=".csv,.xlsx" class="hidden" @change="upload" />
						<FeatherIcon name="upload" class="mr-1 inline h-4 w-4" /> {{ preview ? "Upload another file" : "Choose a CSV or Excel file" }}
					</label>
					<LoadingIndicator v-if="reading" class="h-5 w-5 text-gray-500" />
					<span v-if="preview" class="text-sm text-gray-600">{{ preview.filename }} · {{ preview.rows.length }} rows</span>
				</div>
				<p class="mt-2 text-xs text-gray-500">
					Columns: <code>supplier_name</code>, <code>billing_currency</code> and <code>payment_terms</code> (all three required), then
					<code>supplier_group</code>, <code>country</code>, <code>tax_id</code>, <code>email_id</code>, <code>mobile_no</code>,
					<code>address_line1</code>, <code>city</code>. A name we already have updates that supplier; any other name adds one.
					Payment terms must be one of: {{ terms || "—" }}.
				</p>
			</section>

			<!-- 2. Preview -->
			<template v-if="preview && !result">
				<Chips v-model="filter" :options="chips" />
				<div class="overflow-x-auto rounded-lg border bg-white">
					<table class="w-full text-sm">
						<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
							<tr>
								<th class="px-4 py-2 font-medium">Row</th>
								<th class="px-2 py-2 font-medium">What happens</th>
								<th class="px-2 py-2 font-medium">Supplier</th>
								<th class="px-2 py-2 font-medium">Currency · terms</th>
								<th class="px-4 py-2 font-medium">Detail</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="r in visible" :key="r.row" class="border-t align-top">
								<td class="px-4 py-2 tabular text-gray-500">{{ r.row }}</td>
								<td class="px-2 py-2"><span class="rounded px-1.5 py-0.5 text-xs" :class="THEME[r.status]">{{ LABEL[r.status] }}</span></td>
								<td class="px-2 py-2"><div class="font-medium">{{ r.values.supplier_name || "—" }}</div>
									<div class="text-xs text-gray-500">{{ [r.values.supplier_group, r.values.country].filter(Boolean).join(" · ") }}</div></td>
								<td class="px-2 py-2">{{ r.values.billing_currency || "—" }} · {{ r.values.payment_terms || "—" }}</td>
								<td class="px-4 py-2">
									<div v-for="e in r.errors" :key="e" class="text-red-700">{{ e }}</div>
									<div v-for="c in r.changes" :key="c[0]">
										<span class="text-gray-500">{{ FIELD[c[0]] }}</span>{{ " " }}
										<span>{{ c[1] || "—" }}</span> → <b class="text-blue-800">{{ c[2] }}</b>
									</div>
									<span v-if="r.status === 'new'" class="text-gray-500">{{ [r.values.email_id, r.values.mobile_no, r.values.city].filter(Boolean).join(" · ") }}</span>
								</td>
							</tr>
						</tbody>
					</table>
					<p v-if="!visible.length" class="px-4 py-6 text-sm text-gray-500">No rows here.</p>
				</div>
			</template>

			<!-- 3. Result -->
			<section v-if="result" class="space-y-3 rounded-lg border bg-white p-4 text-sm">
				<h3 class="text-base font-semibold">Done</h3>
				<p><b>{{ result.created }}</b> suppliers added, <b>{{ result.updated }}</b> updated<template v-if="result.failed">, <b class="text-red-700">{{ result.failed }}</b> failed</template>.</p>
				<ul v-if="result.failed_rows.length" class="space-y-1">
					<li v-for="r in result.failed_rows" :key="r.row">Row {{ r.row }} · {{ r.supplier_name }}: {{ r.reason }}</li>
				</ul>
				<Button label="Upload another file" @click="reset" />
			</section>
		</div>

		<div v-if="preview && !result" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
				<div class="min-w-0 flex-1 text-sm">
					<b>{{ toApply }}</b> to apply: {{ preview.totals.new }} new, {{ preview.totals.changed }} updated.
					<span class="text-gray-500">{{ preview.totals.unchanged }} unchanged and {{ preview.totals.error }} with errors are left alone.</span>
				</div>
				<Button label="Cancel" @click="reset" />
				<Button variant="solid" :label="`Apply ${toApply}`" :disabled="!toApply" :loading="applying" @click="apply" />
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { call, FeatherIcon, LoadingIndicator, toast } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import { errorMessages } from "@/utils/api"

const M = "erp_overrides.api.suppliers"
const LABEL = { new: "New", changed: "Updated", unchanged: "Unchanged", error: "Error" }
const THEME = { new: "bg-blue-50 text-blue-800", changed: "bg-amber-50 text-amber-900", unchanged: "bg-gray-100 text-gray-600", error: "bg-red-50 text-red-800" }
const FIELD = { supplier_group: "Group", country: "Country", billing_currency: "Billing currency", payment_terms: "Payment terms",
	tax_id: "Tax ID", email_id: "Email", mobile_no: "Phone", address_line1: "Address" }

const preview = ref(null)
const result = ref(null)
const reading = ref(false)
const applying = ref(false)
const filter = ref("todo")
const gaps = ref(null)
const terms = ref("")

const toApply = computed(() => (preview.value ? preview.value.totals.new + preview.value.totals.changed : 0))
const chips = computed(() => {
	const t = preview.value?.totals || {}
	return [
		{ value: "todo", label: "To apply", count: (t.new || 0) + (t.changed || 0) },
		{ value: "error", label: "Errors", count: t.error }, { value: "unchanged", label: "Unchanged", count: t.unchanged },
		{ value: "all", label: "All", count: preview.value?.rows.length },
	]
})
const visible = computed(() => (preview.value?.rows || []).filter((r) =>
	filter.value === "all" || r.status === filter.value || (filter.value === "todo" && ["new", "changed"].includes(r.status))))

const fail = (e, title) => toast({ title, text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600", timeout: 8 })

async function loadGaps() {
	gaps.value = await call(`${M}.get_supplier_gaps`).catch(() => null)
}
onMounted(async () => {
	loadGaps()
	const t = await call("frappe.client.get_list", { doctype: "Payment Terms Template", pluck: "name", limit_page_length: 50 }).catch(() => [])
	terms.value = t.map((x) => x.name || x).join(", ")
})

function template() {
	window.location.href = `/api/method/${M}.template`
}

async function upload(ev) {
	const file = ev.target.files[0]
	ev.target.value = ""
	if (!file) return
	reading.value = true
	result.value = null
	try {
		const content = await new Promise((resolve, reject) => {
			const r = new FileReader()
			r.onload = () => resolve(String(r.result).split(",")[1])
			r.onerror = reject
			r.readAsDataURL(file)
		})
		preview.value = await call(`${M}.preview_import`, { filename: file.name, content })
		filter.value = toApply.value ? "todo" : preview.value.totals.error ? "error" : "all"
	} catch (e) {
		fail(e, "Could not read the file")
	} finally {
		reading.value = false
	}
}

async function apply() {
	applying.value = true
	try {
		result.value = await call(`${M}.apply_import`, { token: preview.value.token })
		toast({ title: "Suppliers uploaded", text: `${result.value.created} added, ${result.value.updated} updated`, icon: "check", iconClasses: "text-green-600" })
		loadGaps()
	} catch (e) {
		fail(e, "Upload not applied")
	} finally {
		applying.value = false
	}
}

function reset() {
	preview.value = null
	result.value = null
}
</script>
