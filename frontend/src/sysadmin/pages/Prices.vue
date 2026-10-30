<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Items & prices" :subtitle="data ? `${data.total} items` : ''">
			<Button icon-left="download" label="Export" @click="exportOpen = true" />
			<Button variant="solid" icon-left="upload" label="Import" @click="$router.push('/prices/import')" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] space-y-3 p-4 pb-28 lg:p-6 lg:pb-28">
			<!-- Price lists shown as columns -->
			<div class="flex flex-wrap items-center gap-1.5">
				<span class="mr-1 text-sm text-gray-600">Price lists:</span>
				<button v-for="pl in lists" :key="pl.name" class="rounded-full border px-3 py-1 text-sm"
					:class="shown.includes(pl.name) ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'"
					@click="toggleList(pl.name)">
					{{ pl.name }} <span class="opacity-70">{{ pl.currency }}</span>
					<span v-if="pl.name === defaults.selling" class="ml-1 text-xs opacity-70">· default selling</span>
					<span v-else-if="pl.name === defaults.buying" class="ml-1 text-xs opacity-70">· default buying</span>
				</button>
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<input v-model="search" class="form-input w-full sm:w-72" placeholder="Search item code or name" aria-label="Search items" />
				<div class="w-full sm:w-60"><LinkField v-model="itemGroup" doctype="Item Group" placeholder="Any item group" /></div>
				<select v-model="missing" class="form-select w-full sm:w-60" aria-label="Only items without a price">
					<option value="">With or without a price</option>
					<option v-for="pl in lists" :key="pl.name" :value="pl.name">No price in {{ pl.name }}</option>
				</select>
				<label class="flex items-center gap-1.5 text-sm"><input v-model="disabled" type="checkbox" class="form-checkbox" /> Disabled items</label>
			</div>

			<p class="text-xs text-gray-500">Click a price to change it. A cell that says “3 prices” has prices per customer, unit or date: click it to see and edit each one.</p>

			<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<div v-else class="overflow-x-auto rounded-lg border bg-white">
				<table class="w-full text-sm">
					<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
						<tr>
							<th class="px-4 py-2 font-medium">Item</th>
							<th class="px-2 py-2 font-medium">Group</th>
							<th class="px-2 py-2 font-medium">Unit</th>
							<th v-for="pl in shown" :key="pl" class="px-3 py-2 text-right font-medium">{{ pl }} <span class="normal-case text-gray-400">{{ currency(pl) }}</span></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="i in data.items" :key="i.item_code" class="border-t" :class="i.disabled && 'text-gray-400'">
							<td class="px-4 py-1.5">
								<div class="font-medium">{{ i.item_name }}</div>
								<div class="text-xs text-gray-500">{{ i.item_code }}</div>
							</td>
							<td class="px-2 py-1.5 text-gray-600">{{ i.item_group }}</td>
							<td class="px-2 py-1.5 text-gray-600">{{ i.stock_uom }}</td>
							<td v-for="pl in shown" :key="pl" class="px-1 py-1 text-right">
								<template v-if="i.prices[pl]">
									<input v-if="isEditing(i, pl)" ref="editor" v-model="edit.value" type="number" min="0" step="any"
										class="form-input w-28 text-right tabular" :aria-label="`${i.item_name} in ${pl}`"
										@keydown.enter.prevent="ready && save()" @keydown.esc="cancel" />
									<button v-else-if="i.prices[pl].editable" class="w-28 rounded px-2 py-1 text-right tabular hover:bg-gray-100"
										:class="saved[`${i.item_code}|${pl}`] ? 'bg-green-50 font-medium text-green-800' : ''" @click="start(i, pl)">
										{{ i.prices[pl].count ? rate(i.prices[pl].rate) : "—" }}
									</button>
									<button v-else class="w-28 rounded px-2 py-1 text-right text-blue-700 hover:bg-blue-50" @click="openPanel(i, pl)">
										{{ i.prices[pl].count }} prices
									</button>
								</template>
							</td>
						</tr>
					</tbody>
				</table>
				<div v-if="data.items.length < data.total" class="border-t p-2 text-center">
					<Button label="Load more" :loading="loading" @click="load(true)" />
				</div>
			</div>
		</div>

		<!-- What is about to change -->
		<div v-if="edit" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
				<div class="min-w-0 flex-1 text-sm">
					<span class="text-gray-500">Item</span> <b class="font-medium">{{ edit.item.item_code }}</b>
					<span class="text-gray-500"> · {{ edit.item.item_name }} · Price list</span> <b class="font-medium">{{ edit.priceList }}</b>
					<span class="text-gray-500"> ({{ edit.currency }}) · per</span> <b class="font-medium">{{ edit.uom }}</b><span class="text-gray-500"> · </span>
					<span class="tabular">{{ edit.old === null ? "no price yet" : rate(edit.old) }}</span> →
					<b class="tabular" :class="ready ? 'text-blue-800' : 'text-gray-400'">{{ edit.value === "" ? "…" : rate(edit.value) }}</b>
					<span v-if="edit.old === null" class="text-gray-500"> (creates the item's first price in this list)</span>
				</div>
				<Button label="Cancel" @click="cancel" />
				<Button variant="solid" label="Save (Enter)" :disabled="!ready" :loading="saving" @click="save" />
			</div>
		</div>

		<!-- Every price for one item in one list -->
		<Dialog v-model="panelOpen" :options="{ title: panel ? `${panel.item.item_name} · ${panel.priceList}` : '', size: '3xl' }">
			<template #body-content>
				<div v-if="panel" class="space-y-4 text-sm">
					<table class="w-full">
						<thead class="text-left text-xs uppercase tracking-wide text-gray-500">
							<tr><th class="py-1">Rate</th><th>Unit</th><th>For</th><th>Valid</th><th /></tr>
						</thead>
						<tbody>
							<tr v-for="p in panel.prices" :key="p.name" class="border-t">
								<td class="py-1.5">
									<input v-if="panel.editing === p.name" v-model="panel.value" type="number" min="0" step="any" class="form-input w-28 text-right tabular" @keydown.enter.prevent="savePanel(p)" @keydown.esc="panel.editing = null" />
									<span v-else class="tabular">{{ rate(p.price_list_rate, p.currency) }}</span>
								</td>
								<td>{{ p.uom }}</td>
								<td>{{ p.customer ? `Customer ${p.customer}` : p.supplier ? `Supplier ${p.supplier}` : p.batch_no ? `Batch ${p.batch_no}` : "Everyone" }}</td>
								<td class="text-gray-600">{{ p.valid_from ? date(p.valid_from) : "always" }}{{ p.valid_upto ? ` – ${date(p.valid_upto)}` : "" }}</td>
								<td class="text-right">
									<template v-if="panel.editing === p.name">
										<span class="mr-2 text-xs text-gray-500">{{ rate(p.price_list_rate) }} → <b class="text-blue-800">{{ rate(panel.value) }}</b></span>
										<Button size="sm" variant="solid" label="Save" :loading="saving" :disabled="panel.value === '' || Number(panel.value) === p.price_list_rate" @click="savePanel(p)" />
									</template>
									<button v-else class="text-blue-700 hover:underline" @click="(panel.editing = p.name), (panel.value = p.price_list_rate)">Change</button>
								</td>
							</tr>
						</tbody>
					</table>
					<div>
						<div class="mb-1 font-medium">Who changed what</div>
						<p v-if="!panel.history.length" class="text-gray-500">No changes recorded.</p>
						<ul v-else class="space-y-1">
							<li v-for="(h, n) in panel.history" :key="n" class="text-gray-700">{{ h.by }} changed {{ h.field.replace(/_/g, " ") }} {{ h.old ?? "—" }} → <b>{{ h.new ?? "—" }}</b> <span class="text-gray-500">· {{ relative(h.when) }}</span></li>
						</ul>
					</div>
				</div>
			</template>
		</Dialog>

		<!-- Export -->
		<Dialog v-model="exportOpen" :options="{ title: 'Export item prices', size: 'lg' }">
			<template #body-content>
				<div class="space-y-4 text-sm">
					<div>
						<div class="mb-1.5 text-gray-600">Price lists</div>
						<div class="flex flex-wrap gap-2">
							<label v-for="pl in lists" :key="pl.name" class="flex items-center gap-1.5 rounded border px-2 py-1">
								<input v-model="exp.lists" type="checkbox" class="form-checkbox" :value="pl.name" /> {{ pl.name }} <span class="text-gray-400">{{ pl.prices }}</span>
							</label>
						</div>
					</div>
					<div><div class="mb-1.5 text-gray-600">Item group</div><LinkField v-model="exp.itemGroup" doctype="Item Group" placeholder="All item groups" /></div>
					<label class="flex items-center gap-2"><input v-model="exp.missing" type="checkbox" class="form-checkbox" /> Also list items with no price yet (rate left blank, to fill in and import)</label>
					<div class="flex gap-4">
						<label class="flex items-center gap-1.5"><input v-model="exp.fmt" type="radio" value="xlsx" /> Excel</label>
						<label class="flex items-center gap-1.5"><input v-model="exp.fmt" type="radio" value="csv" /> CSV</label>
					</div>
					<p class="text-xs text-gray-500">Keep the <b>item_price_id</b> column: import uses it to update exactly that price. Item name and currency are for reading only.</p>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Download" :disabled="!exp.lists.length" @click="doExport" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { Dialog, LoadingIndicator, debounce } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import LinkField from "@/components/LinkField.vue"
import { date, relative } from "@/utils/format"
import { boot } from "@/boot"
import { adm, download, fail, ok, rate } from "../api"

const route = useRoute()
const lists = ref([])
const defaults = reactive({ selling: boot.selling_price_list, buying: boot.buying_price_list })
const shown = ref([])
const search = ref("")
const itemGroup = ref("")
const missing = ref(route.query.missing || "")
const disabled = ref(false)
const data = ref(null)
const loading = ref(false)
const saved = reactive({})

const currency = (pl) => lists.value.find((l) => l.name === pl)?.currency || ""

async function loadLists() {
	const res = await adm("get_price_lists")
	lists.value = res.lists.filter((l) => l.enabled)
	Object.assign(defaults, { selling: res.selling_default, buying: res.buying_default })
	shown.value = [res.selling_default, res.buying_default].filter(Boolean)
	if (missing.value && !shown.value.includes(missing.value)) shown.value.unshift(missing.value)
}

async function load(more = false) {
	if (!shown.value.length) return (data.value = { items: [], total: 0 })
	loading.value = true
	try {
		const res = await adm("get_items", { price_lists: shown.value, search: search.value, item_group: itemGroup.value,
			disabled: disabled.value ? 1 : 0, missing_in: missing.value, start: more ? data.value.items.length : 0 })
		data.value = more ? { ...res, items: [...data.value.items, ...res.items] } : res
	} catch (e) {
		fail(e, "Could not load items")
	} finally {
		loading.value = false
	}
}
function toggleList(name) {
	shown.value = shown.value.includes(name) ? shown.value.filter((x) => x !== name) : [...shown.value, name]
}
watch([shown, itemGroup, missing, disabled], () => load())
watch(search, debounce(() => load(), 300))
loadLists().then(() => load()).catch((e) => fail(e, "Could not load price lists"))

// Inline edit: one cell at a time, saved only after the strip below says what changes
const edit = ref(null)
const editor = ref(null)
const saving = ref(false)
const isEditing = (i, pl) => edit.value && edit.value.item.item_code === i.item_code && edit.value.priceList === pl
const ready = computed(() => edit.value && edit.value.value !== "" && Number(edit.value.value) >= 0 && Number(edit.value.value) !== edit.value.old)

function start(i, pl) {
	const p = i.prices[pl]
	edit.value = { item: i, priceList: pl, name: p.name, old: p.count ? p.rate : null, value: p.count ? p.rate : "",
		uom: p.uom || i.stock_uom, currency: p.currency || currency(pl) }
	nextTick(() => {
		const el = Array.isArray(editor.value) ? editor.value[0] : editor.value
		el?.focus()
		el?.select()
	})
}
const cancel = () => (edit.value = null)

async function save() {
	const e = edit.value
	saving.value = true
	try {
		const res = await adm("set_price", { item_code: e.item.item_code, price_list: e.priceList, rate: e.value,
			item_price: e.name, expected: e.old })
		e.item.prices[e.priceList] = { count: 1, editable: true, name: res.name, rate: res.rate, uom: res.uom, currency: res.currency }
		saved[`${e.item.item_code}|${e.priceList}`] = true
		ok("Price saved", `${e.item.item_code} · ${e.priceList}: ${rate(res.rate, res.currency)}`)
		edit.value = null
	} catch (err) {
		fail(err, "Price not saved")
	} finally {
		saving.value = false
	}
}

const panelOpen = ref(false)
const panel = ref(null)
async function openPanel(i, pl) {
	try {
		const [prices, history] = await Promise.all([
			adm("get_item_prices", { item_code: i.item_code, price_list: pl }),
			adm("get_price_history", { item_code: i.item_code, price_list: pl }),
		])
		panel.value = { item: i, priceList: pl, prices, history, editing: null, value: "" }
		panelOpen.value = true
	} catch (e) {
		fail(e)
	}
}
async function savePanel(p) {
	saving.value = true
	try {
		const res = await adm("set_price", { item_code: panel.value.item.item_code, price_list: panel.value.priceList,
			rate: panel.value.value, item_price: p.name, expected: p.price_list_rate })
		ok("Price saved", `${panel.value.item.item_code} · ${panel.value.priceList}: ${rate(p.price_list_rate)} → ${rate(res.rate, res.currency)}`)
		await openPanel(panel.value.item, panel.value.priceList)
	} catch (e) {
		fail(e, "Price not saved")
	} finally {
		saving.value = false
	}
}

const exportOpen = ref(false)
const exp = reactive({ lists: [], itemGroup: "", missing: false, fmt: "xlsx" })
watch(shown, (v) => (exp.lists = [...v]), { immediate: true })
function doExport() {
	download("export_prices", { price_lists: exp.lists, item_group: exp.itemGroup, include_missing: exp.missing ? 1 : 0, fmt: exp.fmt })
	exportOpen.value = false
}
</script>
