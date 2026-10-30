<template>
	<Autocomplete
		:model-value="modelValue"
		:options="options"
		:placeholder="placeholder || `Search ${doctype}`"
		:disabled="disabled"
		@update:model-value="select"
		@update:query="onQuery"
	>
		<template v-if="quickCreate" #footer="{ togglePopover }">
			<Button variant="ghost" class="w-full !justify-start" icon-left="plus"
				@click="togglePopover(); $emit('create', { doctype: quickCreate, name: query })">
				Create new {{ quickCreate }}{{ query ? ` “${query}”` : "" }}
			</Button>
		</template>
	</Autocomplete>
</template>

<script setup>
import { ref, watch } from "vue"
import { Autocomplete, call, debounce } from "frappe-ui"

const props = defineProps({
	doctype: { type: String, required: true },
	modelValue: { type: String, default: "" },
	filters: { type: Object, default: () => ({}) },
	quickCreate: { type: String, default: null },
	placeholder: String,
	disabled: Boolean,
	// a whitelisted search taking the same arguments, for users without read access to the doctype
	method: { type: String, default: "frappe.desk.search.search_link" },
})
const emit = defineEmits(["update:modelValue", "create"])

const options = ref([])
const query = ref("")

function select(val) {
	emit("update:modelValue", typeof val === "string" ? val : val?.value || "")
}

async function search(txt) {
	if (!props.doctype) return
	const rows = await call(props.method, {
		doctype: props.doctype,
		txt: txt || "",
		filters: props.filters,
		page_length: 20,
	})
	const mapped = rows.map((r) => {
		const title = r.label && r.label !== r.value ? r.label : r.description?.split(",")[0]
		return { label: title ? `${title} · ${r.value}` : r.value, value: r.value }
	})
	if (props.modelValue && !mapped.find((o) => o.value === props.modelValue)) {
		mapped.unshift({ label: props.modelValue, value: props.modelValue })
	}
	options.value = mapped
}

const onQuery = debounce((q) => {
	query.value = q || ""
	search(query.value)
}, 250)

watch(() => [props.doctype, JSON.stringify(props.filters)], () => search(""), { immediate: true })
watch(() => props.modelValue, (v) => {
	if (v && !options.value.find((o) => o.value === v)) options.value = [{ label: v, value: v }, ...options.value]
})
</script>
