<template>
	<div v-if="!hidden" :class="field.span === 2 ? 'sm:col-span-2' : field.span === 3 ? 'sm:col-span-2 xl:col-span-3' : ''">
		<label class="mb-1.5 block text-sm text-gray-600">
			{{ field.label }}<span v-if="required && !readonly" class="text-red-500"> *</span>
		</label>

		<div v-if="readonly" class="min-h-[28px] py-1 text-base text-gray-900 break-words">
			<template v-if="display">{{ display }}</template>
			<span v-else class="text-gray-400">—</span>
		</div>

		<template v-else>
			<LinkField
				v-if="field.type === 'Link' || field.type === 'DynamicLink'"
				:doctype="linkDoctype"
				:model-value="value"
				:filters="field.filters ? field.filters(doc) : {}"
				:quick-create="quickCreate"
				:placeholder="field.placeholder"
				@update:model-value="set"
				@create="(e) => $emit('quick-create', { ...e, fieldname: field.fieldname })"
			/>
			<select v-else-if="field.type === 'Select'" :value="value" class="form-select w-full" @change="set($event.target.value)">
				<option v-for="o in field.options" :key="o" :value="o">{{ o }}</option>
			</select>
			<label v-else-if="field.type === 'Check'" class="flex min-h-[28px] items-center gap-2 text-base">
				<input type="checkbox" class="form-checkbox" :checked="!!value" @change="set($event.target.checked ? 1 : 0)" />
				{{ field.checkLabel || "Yes" }}
			</label>
			<textarea v-else-if="field.type === 'Text'" :value="value" rows="3" class="form-textarea w-full"
				@input="set($event.target.value)" />
			<input v-else :type="inputType" :value="value" class="form-input w-full"
				:step="field.type === 'Date' ? undefined : 'any'"
				@input="set(numeric ? Number($event.target.value) : $event.target.value)" />
		</template>

		<p v-if="field.help && !readonly" class="mt-1 text-xs text-gray-500">{{ field.help }}</p>
	</div>
</template>

<script setup>
import { computed } from "vue"
import LinkField from "./LinkField.vue"
import { date, money } from "@/utils/format"

const props = defineProps({ field: Object, doc: Object, readonly: Boolean })
const emit = defineEmits(["change", "quick-create"])

const value = computed(() => props.doc[props.field.fieldname] ?? "")
const hidden = computed(() => props.field.hidden?.(props.doc))
const required = computed(() => (typeof props.field.reqd === "function" ? props.field.reqd(props.doc) : props.field.reqd))
const numeric = computed(() => ["Currency", "Percent", "Float", "Int"].includes(props.field.type))
const linkDoctype = computed(() => (props.field.type === "DynamicLink" ? props.doc[props.field.options] : props.field.options))
const quickCreate = computed(() => props.field.quickCreate?.(props.doc) || null)
const inputType = computed(() =>
	props.field.type === "Date" ? "date" : numeric.value ? "number" : props.field.inputType || "text"
)
const display = computed(() => {
	const v = value.value
	if (v === "" || v === null) return ""
	if (props.field.type === "Date") return date(v)
	if (props.field.type === "Currency") return money(v, props.doc.currency)
	if (props.field.type === "Percent") return `${v}%`
	if (props.field.type === "Check") return v ? "Yes" : "No"
	return v
})

const set = (v) => emit("change", props.field.fieldname, v)
</script>
