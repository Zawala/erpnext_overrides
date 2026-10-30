<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Import item prices" subtitle="Upload, check every row, then apply. Nothing changes until you apply." back="/prices">
			<Button icon-left="file" label="Template" @click="template" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] space-y-4 p-4 pb-28 lg:p-6 lg:pb-28">
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
					Columns: <code>item_code</code>, <code>price_list</code>, <code>price_list_rate</code>, and optionally <code>item_price_id</code>,
					<code>uom</code>, <code>valid_from</code>, <code>valid_upto</code>, <code>customer</code>, <code>supplier</code>. Export from Items &amp; prices
					to get a file with every column filled in.
				</p>
			</section>

			<!-- 2. Preview -->
			<template v-if="preview && !result">
				<div class="flex flex-wrap items-center gap-3">
					<Chips v-model="filter" :options="chips" />
					<span v-if="preview.warnings" class="text-sm text-amber-800">{{ preview.warnings }} with warnings</span>
				</div>
				<div class="overflow-x-auto rounded-lg border bg-white">
					<table class="w-full text-sm">
						<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
							<tr>
								<th class="px-4 py-2 font-medium">Row</th>
								<th class="px-2 py-2 font-medium">What happens</th>
								<th class="px-2 py-2 font-medium">Item</th>
								<th class="px-2 py-2 font-medium">Price list</th>
								<th class="px-2 py-2 font-medium">Unit</th>
								<th class="px-4 py-2 font-medium">Change</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="r in visible" :key="r.row" class="border-t align-top">
								<td class="px-4 py-2 tabular text-gray-500">{{ r.row }}</td>
								<td class="px-2 py-2"><span class="rounded px-1.5 py-0.5 text-xs" :class="THEME[r.status]">{{ LABEL[r.status] }}</span></td>
								<td class="px-2 py-2"><div class="font-medium">{{ r.item_code }}</div><div class="text-xs text-gray-500">{{ r.item_name }}</div></td>
								<td class="px-2 py-2">{{ r.price_list }} <span class="text-gray-400">{{ r.currency }}</span></td>
								<td class="px-2 py-2">{{ r.uom }}</td>
								<td class="px-4 py-2">
									<div v-for="e in r.errors" :key="e" class="text-red-700">{{ e }}</div>
									<template v-if="r.status === 'new'">
										<b class="tabular">{{ rate(r.values.price_list_rate, r.currency) }}</b>
										<span v-if="r.values.customer" class="text-gray-500"> for {{ r.values.customer }}</span>
										<span v-if="r.values.supplier" class="text-gray-500"> from {{ r.values.supplier }}</span>
										<span v-if="r.values.valid_from" class="text-gray-500"> from {{ date(r.values.valid_from) }}</span>
									</template>
									<div v-for="c in r.changes" :key="c[0]">
										<span class="text-gray-500">{{ FIELD[c[0]] }}</span>{{ " " }}
										<span class="tabular">{{ show(c[0], c[1], r.currency) }}</span> → <b class="tabular text-blue-800">{{ show(c[0], c[2], r.currency) }}</b>
									</div>
									<div v-for="w in r.warnings" :key="w" class="text-amber-800">{{ w }}</div>
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
				<p><b>{{ result.updated }}</b> prices changed, <b>{{ result.created }}</b> added<template v-if="result.skipped">, <b class="text-amber-800">{{ result.skipped }}</b> skipped</template><template v-if="result.failed">, <b class="text-red-700">{{ result.failed }}</b> failed</template>.</p>
				<div v-if="result.skipped_rows.length || result.failed_rows.length">
					<ul class="space-y-1">
						<li v-for="r in [...result.skipped_rows, ...result.failed_rows]" :key="r.row">Row {{ r.row }} · {{ r.item_code }}: {{ r.reason }}</li>
					</ul>
					<Button class="mt-2" icon-left="download" label="Download these rows" @click="downloadProblems" />
				</div>
				<div class="flex gap-2">
					<Button label="Back to prices" @click="$router.push('/prices')" />
					<Button label="Import another file" @click="reset" />
				</div>
			</section>
		</div>

		<div v-if="preview && !result" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
				<div class="min-w-0 flex-1 text-sm">
					<b>{{ toApply }}</b> to apply: {{ preview.totals.changed }} changed, {{ preview.totals.new }} new.
					<span class="text-gray-500">{{ preview.totals.unchanged }} unchanged and {{ preview.totals.error }} with errors are left alone.</span>
				</div>
				<Button label="Cancel" @click="reset" />
				<Button variant="solid" :label="`Apply ${toApply} change${toApply === 1 ? '' : 's'}`" :disabled="!toApply" @click="confirmOpen = true" />
			</div>
		</div>

		<Dialog v-model="confirmOpen" :options="{ title: `Apply ${toApply} price change${toApply === 1 ? '' : 's'}?`, size: 'md' }">
			<template #body-content>
				<div class="space-y-2 text-sm">
					<p>From <b>{{ preview?.filename }}</b>: {{ preview?.totals.changed }} existing prices change and {{ preview?.totals.new }} new prices are added, in
						{{ affectedLists.join(", ") }}.</p>
					<p class="text-gray-600">Each change is recorded under your name. A price someone else changes before you apply is skipped, not overwritten.</p>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Apply" :loading="applying" @click="apply" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { Dialog, FeatherIcon, LoadingIndicator } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import { date } from "@/utils/format"
import { adm, download, fail, ok, rate } from "../api"

const LABEL = { new: "New", changed: "Changed", unchanged: "Unchanged", error: "Error" }
const THEME = { new: "bg-blue-50 text-blue-800", changed: "bg-amber-50 text-amber-900", unchanged: "bg-gray-100 text-gray-600", error: "bg-red-50 text-red-800" }
const FIELD = { price_list_rate: "Rate", uom: "Unit", valid_from: "Valid from", valid_upto: "Valid to", customer: "Customer", supplier: "Supplier" }

const preview = ref(null)
const result = ref(null)
const reading = ref(false)
const filter = ref("todo")
const confirmOpen = ref(false)
const applying = ref(false)

const toApply = computed(() => (preview.value ? preview.value.totals.new + preview.value.totals.changed : 0))
const chips = computed(() => {
	const t = preview.value?.totals || {}
	return [
		{ value: "todo", label: "To apply", count: (t.new || 0) + (t.changed || 0) },
		{ value: "changed", label: "Changed", count: t.changed }, { value: "new", label: "New", count: t.new },
		{ value: "error", label: "Errors", count: t.error }, { value: "unchanged", label: "Unchanged", count: t.unchanged },
		{ value: "all", label: "All", count: preview.value?.rows.length },
	]
})
const visible = computed(() => (preview.value?.rows || []).filter((r) =>
	filter.value === "all" || r.status === filter.value || (filter.value === "todo" && ["new", "changed"].includes(r.status))))
const affectedLists = computed(() => [...new Set((preview.value?.rows || []).filter((r) => ["new", "changed"].includes(r.status)).map((r) => r.price_list))])

const show = (field, v, currency) => (v === null || v === undefined || v === "" ? "—" : field === "price_list_rate" ? rate(v, currency)
	: field.startsWith("valid") ? date(v) : v)

function template() {
	download("export_prices", { price_lists: [], template: 1, fmt: "xlsx" })
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
		preview.value = await adm("preview_import", { filename: file.name, content })
		filter.value = preview.value.totals.new + preview.value.totals.changed ? "todo" : preview.value.totals.error ? "error" : "all"
	} catch (e) {
		fail(e, "Could not read the file")
	} finally {
		reading.value = false
	}
}

async function apply() {
	applying.value = true
	try {
		result.value = await adm("apply_import", { token: preview.value.token })
		confirmOpen.value = false
		ok("Prices imported", `${result.value.updated} changed, ${result.value.created} added`)
	} catch (e) {
		fail(e, "Import not applied")
	} finally {
		applying.value = false
	}
}

function reset() {
	preview.value = null
	result.value = null
}

function downloadProblems() {
	const rows = [["row", "item_code", "reason"], ...[...result.value.skipped_rows, ...result.value.failed_rows].map((r) => [r.row, r.item_code, r.reason])]
	const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n")
	const a = document.createElement("a")
	a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }))
	a.download = "price-import-problems.csv"
	a.click()
}
</script>
