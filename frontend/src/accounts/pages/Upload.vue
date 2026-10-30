<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Upload a statement" subtitle="CSV, Excel or PDF straight from the bank — lines already in are skipped" back="/bank" />

		<div class="mx-auto w-full max-w-[1400px] p-4 lg:p-6 space-y-4">
			<!-- 1. File -->
			<section class="grid grid-cols-1 gap-4 rounded-lg border bg-white p-4 sm:grid-cols-[1fr_1.4fr_auto] sm:items-end">
				<label>
					<span class="mb-1.5 block text-sm text-gray-600">Bank account</span>
					<select v-model="bankAccount" class="form-select w-full" :disabled="!!preview">
						<option v-for="b in boot.banks" :key="b.name" :value="b.name">{{ b.account_name || b.name }} ({{ b.currency }})</option>
					</select>
				</label>
				<label>
					<span class="mb-1.5 block text-sm text-gray-600">Statement file</span>
					<input type="file" accept=".csv,.xls,.xlsx,.pdf" class="form-input w-full" :disabled="!!preview" @change="file = $event.target.files[0]" />
				</label>
				<Button v-if="!preview" variant="solid" label="Read it" :disabled="!file || !bankAccount" :loading="reading" @click="read" />
				<Button v-else label="Start again" @click="reset" />
			</section>

			<template v-if="preview">
				<!-- 2. Summary -->
				<section class="grid grid-cols-2 gap-3 sm:grid-cols-4">
					<Tile label="Lines found" :value="preview.rows.length" />
					<Tile label="New" :value="preview.new" strong />
					<Tile label="Already imported" :value="preview.duplicates" :hint="preview.duplicates ? 'will be skipped' : ''" />
					<Tile label="Period" :value="preview.start_date ? `${date(preview.start_date)} – ${date(preview.end_date)}` : '—'"
						:hint="preview.closing_balance != null ? `Closing ${cur(preview.closing_balance, preview.currency)}` : ''" />
				</section>

				<!-- 3. Columns -->
				<section v-if="!preview.is_pdf" class="rounded-lg border bg-white">
					<header class="border-b px-4 py-3">
						<h3 class="font-semibold">Columns</h3>
						<p class="text-sm text-gray-500">Read from the header row. Fix any that are wrong — at least a date, a description and the amounts.</p>
					</header>
					<div class="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
						<label v-for="c in columns" :key="c.index">
							<span class="mb-1.5 block truncate text-sm text-gray-600">“{{ c.header || `Column ${c.index + 1}` }}”</span>
							<select v-model="c.maps_to" class="form-select w-full" @change="remap">
								<option v-for="o in preview.options" :key="o">{{ o }}</option>
							</select>
						</label>
					</div>
				</section>

				<!-- 4. Lines -->
				<section class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h3 class="font-semibold">Lines</h3>
						<label class="flex items-center gap-2 text-sm"><input v-model="newOnly" type="checkbox" class="form-checkbox" /> New only</label>
					</header>
					<div class="max-h-[50vh] overflow-y-auto">
						<table class="w-full text-sm tabular">
							<thead class="sticky top-0 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
								<tr><th class="px-4 py-2">Date</th><th class="px-2 py-2">Description</th><th class="px-2 py-2 text-right">Out</th><th class="px-4 py-2 text-right">In</th></tr>
							</thead>
							<tbody>
								<tr v-for="(r, i) in shownRows" :key="i" class="border-t" :class="r.duplicate ? 'text-gray-400' : ''">
									<td class="whitespace-nowrap px-4 py-1.5">{{ date(r.date) }}</td>
									<td class="px-2 py-1.5">{{ r.description }} <span v-if="r.duplicate" class="ml-1 rounded bg-gray-100 px-1 text-xs">already in</span></td>
									<td class="px-2 py-1.5 text-right">{{ r.withdrawal ? r.withdrawal.toFixed(2) : "" }}</td>
									<td class="px-4 py-1.5 text-right text-green-700">{{ r.deposit ? r.deposit.toFixed(2) : "" }}</td>
								</tr>
							</tbody>
						</table>
					</div>
					<footer class="flex flex-wrap items-center justify-end gap-3 border-t px-4 py-3">
						<span class="text-sm text-gray-500">Bank rules run on the new lines straight after.</span>
						<Button variant="solid" :label="`Import ${preview.new} line${preview.new === 1 ? '' : 's'}`" :disabled="!preview.new" :loading="importing" @click="doImport" />
					</footer>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, h, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { boot } from "@/boot"
import { date } from "@/utils/format"
import { acc, cur, ok, fail } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"

const route = useRoute()
const router = useRouter()
const bankAccount = ref(route.query.account || boot.banks?.[0]?.name || "")
const file = ref(null)
const preview = ref(null)
const columns = ref([])
const reading = ref(false)
const importing = ref(false)
const newOnly = ref(false)

const shownRows = computed(() => (preview.value?.rows || []).filter((r) => !newOnly.value || !r.duplicate))

function show(p) {
	preview.value = p
	columns.value = p.columns.map((c) => ({ ...c }))
}

async function read() {
	reading.value = true
	try {
		const fd = new FormData()
		fd.append("file", file.value, file.value.name)
		fd.append("is_private", "1")
		const res = await fetch("/api/method/upload_file", { method: "POST", body: fd, headers: { "X-Frappe-CSRF-Token": window.csrf_token } })
		const body = await res.json()
		if (!res.ok) throw { messages: [body.exception || "Upload failed"] }
		show(await acc("start_import", { bank_account: bankAccount.value, file_url: body.message.file_url }))
	} catch (e) {
		fail(e, "Could not read the statement")
	} finally {
		reading.value = false
	}
}

async function remap() {
	try {
		show(await acc("map_columns", { name: preview.value.name, columns: columns.value }))
	} catch (e) {
		fail(e)
	}
}

async function doImport() {
	importing.value = true
	try {
		const out = await acc("import_statement", { name: preview.value.name })
		ok(`Imported ${out.created} line${out.created === 1 ? "" : "s"}`, out.skipped ? `${out.skipped} already in, skipped` : undefined)
		router.push(`/bank/${encodeURIComponent(bankAccount.value)}`)
	} catch (e) {
		fail(e)
	} finally {
		importing.value = false
	}
}

function reset() {
	preview.value = null
	file.value = null
}

const Tile = (p) => h("div", { class: ["rounded-lg border bg-white px-4 py-3", p.strong ? "border-gray-900" : ""] }, [
	h("div", { class: "text-xs text-gray-500" }, p.label),
	h("div", { class: "mt-0.5 text-lg font-semibold tabular" }, String(p.value)),
	p.hint ? h("div", { class: "text-xs text-gray-400" }, p.hint) : null,
])
Tile.props = ["label", "value", "hint", "strong"]
</script>
