<template>
	<section class="rounded-lg border bg-white">
		<header class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
			<div class="min-w-0">
				<h3 class="text-base font-semibold">{{ config.label }}</h3>
				<p v-if="config.help && !readonly" class="text-xs text-gray-500">{{ config.help }}</p>
			</div>
			<div class="flex shrink-0 gap-2 whitespace-nowrap">
				<slot name="actions" />
				<Button v-if="editable" icon-left="plus" label="Add row" @click="add" />
			</div>
		</header>

		<!-- Desktop / tablet: editable grid -->
		<div class="hidden md:block overflow-x-auto">
			<table class="w-full table-fixed text-base tabular" :style="{ minWidth: `${columns.length * 140}px` }">
				<thead>
					<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
						<th class="w-10 px-4 py-2 font-medium">#</th>
						<th v-for="c in columns" :key="c.fieldname" class="px-2 py-2 font-medium" :class="[alignRight(c) && 'text-right', c.width]">
							{{ c.label }}<span v-if="c.reqd && editable" class="text-red-500"> *</span>
						</th>
						<th v-if="editable" class="w-10"></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, i) in rows" :key="row.name || row._key" class="border-t align-top">
						<td class="px-4 py-2.5 text-gray-400">{{ i + 1 }}</td>
						<td v-for="c in columns" :key="c.fieldname" class="px-2 py-2 min-w-0" :class="alignRight(c) && 'text-right'">
							<Cell :column="c" :row="row" :readonly="!editable || c.readonly" />
						</td>
						<td v-if="editable" class="py-2 pr-2">
							<button class="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-red-600" title="Remove row" @click="remove(i)">
								<FeatherIcon name="trash-2" class="h-4 w-4" />
							</button>
						</td>
					</tr>
				</tbody>
				<tfoot v-if="totals.length && rows.length">
					<tr class="border-t bg-gray-50 font-medium">
						<td class="px-4 py-2"></td>
						<td v-for="c in columns" :key="c.fieldname" class="px-2 py-2" :class="alignRight(c) && 'text-right'">
							{{ c.total ? show(total(c), c) : "" }}
						</td>
						<td v-if="editable"></td>
					</tr>
				</tfoot>
			</table>
		</div>

		<!-- Mobile: cards + row editor -->
		<ul class="md:hidden divide-y">
			<li v-for="(row, i) in rows" :key="row.name || row._key" class="px-4 py-3 active:bg-gray-50" @click="edit(i)">
				<div class="flex items-start justify-between gap-3">
					<div class="min-w-0">
						<div class="truncate font-medium">{{ show(row[columns[0].fieldname], columns[0]) || "New row" }}</div>
						<div class="truncate text-sm text-gray-500">
							{{ columns.slice(1, 3).map((c) => show(row[c.fieldname], c)).filter(Boolean).join(" · ") }}
						</div>
					</div>
					<div v-if="amountColumn" class="shrink-0 font-medium tabular">{{ show(row[amountColumn.fieldname], amountColumn) }}</div>
				</div>
			</li>
		</ul>

		<div v-if="!rows.length" class="px-4 py-8 text-center text-gray-500">
			No rows yet.
			<button v-if="editable" class="text-gray-900 underline" @click="add">Add the first one</button>
		</div>

		<Dialog v-model="editorOpen" :options="{ title: config.label, size: 'md' }">
			<template #body-content>
				<div v-if="editing" class="space-y-4">
					<div v-for="c in columns" :key="c.fieldname">
						<label class="mb-1.5 block text-sm text-gray-600">{{ c.label }}</label>
						<Cell :column="c" :row="editing" :readonly="!editable || c.readonly" />
					</div>
					<div class="flex justify-between pt-2">
						<Button v-if="editable" theme="red" variant="subtle" icon-left="trash-2" label="Remove" @click="remove(editingIndex); editorOpen = false" />
						<Button variant="solid" label="Done" @click="editorOpen = false" />
					</div>
				</div>
			</template>
		</Dialog>
	</section>
</template>

<script setup>
/**
 * An editable child table, configured by columns:
 *   { fieldname, label, type, options, reqd, readonly, total, width }
 *   type: Data | Text | Link | DynamicLink | Select | Currency | Float | Int | Percent | Check | Date
 *   DynamicLink takes its doctype from row[options]; Select options are an array
 * Rows get `doctype` = config.doctype so frappe.client.save knows the child type.
 */
import { computed, h, ref } from "vue"
import { Dialog, FeatherIcon } from "frappe-ui"
import LinkField from "./LinkField.vue"
import { date, money } from "@/utils/format"

const props = defineProps({
	doc: { type: Object, required: true },
	config: { type: Object, required: true },
	readonly: Boolean,
})
const emit = defineEmits(["changed"])

const NUMERIC = ["Currency", "Float", "Int", "Percent"]
const columns = computed(() => props.config.columns)
const editable = computed(() => !props.readonly && !props.config.readonly)
const rows = computed(() => props.doc[props.config.field] || [])
const totals = computed(() => columns.value.filter((c) => c.total))
const amountColumn = computed(() => columns.value.find((c) => c.type === "Currency"))
const alignRight = (c) => NUMERIC.includes(c.type)

const total = (c) => rows.value.reduce((s, r) => s + Number(r[c.fieldname] || 0), 0)
function show(v, c) {
	if (v === undefined || v === null || v === "") return ""
	if (c.type === "Currency") return money(v, props.doc.currency)
	if (c.type === "Date") return date(v)
	if (c.type === "Percent") return `${v}%`
	if (c.type === "Check") return v ? "Yes" : "No"
	return String(v)
}

const editorOpen = ref(false)
const editingIndex = ref(-1)
const editing = computed(() => rows.value[editingIndex.value])

function set(row, c, v) {
	row[c.fieldname] = v
	props.config.onChange?.(row, c.fieldname, props.doc)
	emit("changed")
}

function add() {
	const row = { _key: Math.random().toString(36).slice(2), doctype: props.config.doctype, ...(props.config.defaults?.(props.doc) || {}) }
	if (!props.doc[props.config.field]) props.doc[props.config.field] = []
	props.doc[props.config.field].push(row)
	emit("changed")
	if (window.matchMedia("(max-width: 767px)").matches) edit(rows.value.length - 1)
}

function remove(i) {
	props.doc[props.config.field].splice(i, 1)
	props.doc[props.config.field].forEach((r, idx) => (r.idx = idx + 1))
	emit("changed")
}

function edit(i) {
	editingIndex.value = i
	editorOpen.value = true
}

const Cell = (p) => {
	const { column: c, row } = p
	const v = row[c.fieldname]
	if (p.readonly) return h("div", { class: "py-0.5 break-words" }, show(v, c) || "—")
	if (c.type === "Link" || c.type === "DynamicLink") {
		const doctype = c.type === "DynamicLink" ? row[c.options] : c.options
		if (!doctype) return h("div", { class: "py-1 text-sm text-gray-400" }, "Pick the type first")
		return h(LinkField, {
			doctype, modelValue: v || "", filters: c.filters ? c.filters(row, props.doc) : {},
			// the default "Search <doctype>" wraps in a narrow cell
			placeholder: c.placeholder || "Search",
			"onUpdate:modelValue": (val) => set(row, c, val),
		})
	}
	if (c.type === "Select") {
		return h("select", { value: v ?? "", class: "form-select w-full", onChange: (e) => set(row, c, e.target.value) },
			c.options.map((o) => h("option", { value: o }, o)))
	}
	if (c.type === "Check") {
		return h("input", { type: "checkbox", checked: !!v, class: "form-checkbox mt-1.5", onChange: (e) => set(row, c, e.target.checked ? 1 : 0) })
	}
	if (c.type === "Text") {
		return h("textarea", { value: v ?? "", rows: 1, class: "form-textarea w-full", onInput: (e) => set(row, c, e.target.value) })
	}
	const numeric = NUMERIC.includes(c.type)
	return h("input", {
		type: c.type === "Date" ? "date" : numeric ? "number" : "text",
		step: numeric ? "any" : undefined,
		inputmode: numeric ? "decimal" : undefined,
		value: v ?? "",
		class: ["form-input w-full", numeric && "text-right tabular"],
		onInput: (e) => {
			if (!numeric) return set(row, c, e.target.value)
			const n = parseFloat(e.target.value)
			set(row, c, Number.isFinite(n) ? n : 0)
		},
	})
}
Cell.props = ["column", "row", "readonly"]
</script>
