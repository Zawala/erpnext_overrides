<template>
	<section class="rounded-lg border bg-white">
		<header class="flex items-center justify-between gap-3 border-b px-4 py-3">
			<div>
				<h3 class="text-base font-semibold">Lines</h3>
				<p v-if="config.mode === 'buying' && !readonly" class="text-xs text-gray-500">
					{{ rateLabel }} is the rate we pay, not the rate we charge.
				</p>
				<p v-else-if="config.qtyHint && !readonly" class="text-xs text-gray-500">{{ config.qtyHint }}</p>
			</div>
			<Button v-if="!readonly" icon-left="plus" label="Add line" @click="addLine" />
		</header>

		<!-- Desktop / tablet: editable grid -->
		<div class="hidden md:block overflow-x-auto">
			<table class="w-full min-w-[720px] table-fixed text-base tabular">
				<thead>
					<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
						<th class="w-10 px-4 py-2 font-medium">#</th>
						<th class="px-2 py-2 font-medium">Item</th>
						<th class="w-24 px-2 py-2 font-medium text-right">Qty</th>
						<th class="w-36 px-2 py-2 font-medium text-right">{{ rateLabel }}</th>
						<th v-if="config.discount" class="w-24 px-2 py-2 font-medium text-right">Disc %</th>
						<th class="w-36 px-2 py-2 font-medium text-right">Amount</th>
						<th v-if="!readonly" class="w-10"></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, i) in doc.items" :key="row.name || row._key" class="border-t align-top">
						<td class="px-4 py-2.5 text-gray-400">{{ i + 1 }}</td>
						<td class="px-2 py-2 min-w-0">
							<LinkField v-if="!readonly" doctype="Item" :model-value="row.item_code"
								:filters="itemFilters" @update:model-value="(v) => setItem(row, v)" />
							<div v-else class="font-medium py-0.5">{{ row.item_code }}</div>
							<div v-if="row.item_name && row.item_name !== row.item_code" class="mt-1 text-sm text-gray-500 line-clamp-2">
								{{ row.item_name }}
							</div>
							<!-- a supplier bill line booked straight to an account has no item -->
							<div v-else-if="!row.item_code && row.description" class="mt-1 text-sm text-gray-500 line-clamp-2">
								{{ String(row.description).replace(/<[^>]+>/g, "") }}{{ row.expense_account ? ` · ${row.expense_account}` : "" }}
							</div>
							<div v-if="discountOver(row)" class="mt-1 text-xs text-amber-700">
								Over the {{ boot.limits.discount_limit }}% discount limit — needs Discount Approved
							</div>
						</td>
						<td class="px-2 py-2 text-right">
							<NumInput v-if="!readonly" :value="row.qty" @set="(v) => setQty(row, v)" />
							<span v-else>{{ row.qty }} <span class="text-gray-400 text-sm">{{ row.uom }}</span></span>
						</td>
						<td class="px-2 py-2 text-right">
							<NumInput v-if="!readonly" :value="row.rate" @set="(v) => setRate(row, v)" />
							<span v-else>{{ money(row.rate, doc.currency) }}</span>
							<div v-if="row.price_list_rate && row.price_list_rate !== row.rate" class="mt-1 text-xs text-gray-400 line-through">
								{{ money(row.price_list_rate, doc.currency) }}
							</div>
						</td>
						<td v-if="config.discount" class="px-2 py-2 text-right">
							<NumInput v-if="!readonly" :value="row.discount_percentage" @set="(v) => setDiscount(row, v)" />
							<span v-else>{{ row.discount_percentage ? `${row.discount_percentage}%` : "—" }}</span>
						</td>
						<td class="px-2 py-2.5 text-right font-medium">{{ money(row.amount, doc.currency) }}</td>
						<td v-if="!readonly" class="py-2 pr-2">
							<button class="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-red-600" title="Remove line"
								@click="remove(i)">
								<FeatherIcon name="trash-2" class="h-4 w-4" />
							</button>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- Mobile: cards + line editor -->
		<ul class="md:hidden divide-y">
			<li v-for="(row, i) in doc.items" :key="row.name || row._key" class="px-4 py-3 active:bg-gray-50"
				@click="!readonly && edit(i)">
				<div class="flex items-start justify-between gap-3">
					<div class="min-w-0">
						<div class="font-medium text-base truncate">{{ row.item_name || row.item_code || "New line" }}</div>
						<div class="mt-0.5 text-sm text-gray-500 tabular">
							{{ row.qty }} × {{ money(row.rate, doc.currency) }}
							<span v-if="row.discount_percentage"> · {{ row.discount_percentage }}% off</span>
						</div>
						<div v-if="discountOver(row)" class="mt-0.5 text-xs text-amber-700">Over discount limit</div>
					</div>
					<div class="text-right font-medium tabular">{{ money(row.amount, doc.currency) }}</div>
				</div>
			</li>
		</ul>

		<div v-if="!doc.items?.length" class="px-4 py-10 text-center text-gray-500">
			No lines yet.
			<button v-if="!readonly" class="text-gray-900 underline" @click="addLine">Add the first one</button>
		</div>

		<Dialog v-model="editorOpen" :options="{ title: 'Line', size: 'md' }">
			<template #body-content>
				<div v-if="editing" class="space-y-4">
					<div>
						<label class="mb-1.5 block text-sm text-gray-600">Item</label>
						<LinkField doctype="Item" :model-value="editing.item_code" :filters="itemFilters"
							@update:model-value="(v) => setItem(editing, v)" />
						<p v-if="editing.item_name" class="mt-1 text-sm text-gray-500">{{ editing.item_name }}</p>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label class="mb-1.5 block text-sm text-gray-600">Qty</label>
							<NumInput :value="editing.qty" @set="(v) => setQty(editing, v)" />
						</div>
						<div>
							<label class="mb-1.5 block text-sm text-gray-600">{{ rateLabel }}</label>
							<NumInput :value="editing.rate" @set="(v) => setRate(editing, v)" />
						</div>
						<div v-if="config.discount">
							<label class="mb-1.5 block text-sm text-gray-600">Discount %</label>
							<NumInput :value="editing.discount_percentage" @set="(v) => setDiscount(editing, v)" />
						</div>
						<div>
							<label class="mb-1.5 block text-sm text-gray-600">Amount</label>
							<div class="py-1 font-medium tabular">{{ money(editing.amount, doc.currency) }}</div>
						</div>
					</div>
				</div>
			</template>
			<template #actions>
				<div class="flex gap-2">
					<Button theme="red" variant="subtle" label="Remove" @click="remove(editingIndex); editorOpen = false" />
					<Button variant="solid" class="flex-1" label="Done" @click="editorOpen = false" />
				</div>
			</template>
		</Dialog>
	</section>
</template>

<script setup>
import { computed, ref, h } from "vue"
import { Dialog, FeatherIcon } from "frappe-ui"
import LinkField from "./LinkField.vue"
import { boot } from "@/boot"
import { api, errorMessages } from "@/utils/api"
import { money } from "@/utils/format"
import { toast } from "frappe-ui"

const props = defineProps({
	doc: { type: Object, required: true },
	config: { type: Object, required: true },
	readonly: Boolean,
	propagate: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["changed"])

const rateLabel = computed(() => props.config.rateLabel || "Rate")
const itemFilters = computed(() =>
	props.config.mode === "buying" ? { is_purchase_item: 1, disabled: 0 } : { is_sales_item: 1, disabled: 0 }
)

const editorOpen = ref(false)
const editingIndex = ref(-1)
const editing = computed(() => props.doc.items?.[editingIndex.value])

const round = (n, p = 2) => Math.round((Number(n) || 0) * 10 ** p) / 10 ** p
const touch = () => emit("changed")

const discountOver = (row) =>
	props.config.discount && boot.limits?.discount_limit && Number(row.discount_percentage || 0) > boot.limits.discount_limit

function recalc(row) {
	row.amount = round(Number(row.qty || 0) * Number(row.rate || 0))
	touch()
}

function setQty(row, v) {
	row.qty = v
	recalc(row)
}

// Same behaviour as desk: a rate below the list price is recorded as a discount,
// which is what the discount-approval rule checks.
function setRate(row, v) {
	row.rate = v
	const plr = Number(row.price_list_rate || 0)
	if (props.config.discount && plr > 0) {
		row.discount_percentage = v < plr ? round((1 - v / plr) * 100, 3) : 0
	}
	recalc(row)
}

function setDiscount(row, v) {
	row.discount_percentage = v
	const plr = Number(row.price_list_rate || 0)
	if (plr > 0) row.rate = round(plr * (1 - v / 100))
	recalc(row)
}

async function setItem(row, itemCode) {
	row.item_code = itemCode
	if (!itemCode) return touch()
	try {
		const d = await api("get_item_details", { doc: { ...props.doc, items: undefined }, item_code: itemCode })
		Object.assign(row, {
			item_name: d.item_name,
			description: d.description,
			uom: d.uom,
			stock_uom: d.stock_uom,
			conversion_factor: d.conversion_factor || 1,
			price_list_rate: d.price_list_rate || 0,
			rate: d.rate || d.price_list_rate || 0,
			discount_percentage: props.config.discount ? d.discount_percentage || 0 : undefined,
		})
		if (!row.qty) row.qty = 1
	} catch (e) {
		toast({ title: "Could not price item", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600" })
	}
	recalc(row)
}

function addLine() {
	const row = { _key: Math.random().toString(36).slice(2), doctype: childDoctype(), qty: 1, rate: 0, amount: 0 }
	for (const [parentField, childField] of Object.entries(props.propagate)) {
		if (props.doc[parentField]) row[childField] = props.doc[parentField]
	}
	if (!props.doc.items) props.doc.items = []
	props.doc.items.push(row)
	touch()
	if (window.matchMedia("(max-width: 767px)").matches) edit(props.doc.items.length - 1)
}

function remove(i) {
	props.doc.items.splice(i, 1)
	props.doc.items.forEach((r, idx) => (r.idx = idx + 1))
	touch()
}

function edit(i) {
	editingIndex.value = i
	editorOpen.value = true
}

function childDoctype() {
	return { Quotation: "Quotation Item", "Sales Order": "Sales Order Item", Opportunity: "Opportunity Item",
		"Delivery Note": "Delivery Note Item", "Sales Invoice": "Sales Invoice Item", "Purchase Invoice": "Purchase Invoice Item",
		"Purchase Order": "Purchase Order Item", "Purchase Receipt": "Purchase Receipt Item" }[props.doc.doctype]
}

// Number input that only commits on a parseable value
const NumInput = (p, { emit: e }) =>
	h("input", {
		type: "number",
		step: "any",
		inputmode: "decimal",
		value: p.value ?? "",
		class: "form-input w-full text-right tabular",
		onInput: (ev) => {
			const n = parseFloat(ev.target.value)
			e("set", Number.isFinite(n) ? n : 0)
		},
	})
NumInput.props = ["value"]
NumInput.emits = ["set"]
</script>
