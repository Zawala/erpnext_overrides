<template>
	<div class="space-y-4">
		<div v-if="!types" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<template v-else>
			<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
				<button v-for="t in types" :key="t.doctype" class="flex items-start gap-3 rounded-lg border bg-white p-4 text-left"
					:class="[allowed(t) ? 'hover:border-gray-400' : 'opacity-60 cursor-not-allowed', modelValue === t.doctype && 'border-gray-900 ring-1 ring-gray-900']"
					:disabled="!allowed(t)" @click="$emit('update:modelValue', t.doctype)">
					<span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-gray-100"><FeatherIcon :name="t.icon" class="h-5 w-5 text-gray-700" /></span>
					<span class="min-w-0 flex-1">
						<span class="flex items-center gap-2 font-medium">{{ t.label }}
							<span v-if="t.advanced" class="rounded bg-amber-50 px-1.5 py-0.5 text-xs font-normal text-amber-900">Advanced</span>
						</span>
						<span class="mt-0.5 block text-sm text-gray-600">{{ t.help }}</span>
						<span class="mt-1 block text-xs text-gray-500">
							<template v-if="allowed(t)">{{ t.count.toLocaleString() }} in the system</template>
							<template v-else>You have no {{ mode }} permission on {{ t.doctype }}. The Permission inspector shows how to add it.</template>
						</span>
					</span>
				</button>
				<router-link v-if="mode === 'import'" to="/prices/import" class="flex items-start gap-3 rounded-lg border border-dashed bg-white p-4 hover:border-gray-400">
					<span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-gray-100"><FeatherIcon name="tag" class="h-5 w-5 text-gray-700" /></span>
					<span class="min-w-0 flex-1">
						<span class="font-medium">Item prices</span>
						<span class="mt-0.5 block text-sm text-gray-600">Prices have their own import, which shows every change before applying it.</span>
						<span class="mt-1 block text-xs text-blue-700">Open Import prices →</span>
					</span>
				</router-link>
			</div>

			<details class="rounded-lg border bg-white" :open="isOther">
				<summary class="cursor-pointer px-4 py-3 text-sm font-medium">Something else? Search every record type</summary>
				<div class="space-y-2 border-t p-4">
					<input v-model="search" class="form-input w-full sm:w-80" placeholder="e.g. Warehouse, Project, Holiday List" aria-label="Search record types" />
					<div class="flex flex-wrap gap-1.5">
						<button v-for="d in others" :key="d.doctype" class="rounded-full border px-3 py-1 text-sm"
							:class="modelValue === d.doctype ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'"
							@click="$emit('update:modelValue', d.doctype)">
							{{ d.doctype }} <span class="opacity-60">{{ d.module }}</span>
						</button>
						<span v-if="!others.length" class="text-sm text-gray-500">Nothing matches.</span>
					</div>
					<p class="text-xs text-gray-500">These have no tailored help: download the template and check the columns carefully.</p>
				</div>
			</details>
		</template>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { FeatherIcon, LoadingIndicator, debounce } from "frappe-ui"
import { adm, fail } from "../api"

const props = defineProps({ modelValue: String, mode: { type: String, default: "import" } })
defineEmits(["update:modelValue"])

const types = ref(null)
const others = ref([])
const search = ref("")

adm("get_data_types").then((d) => (types.value = d)).catch((e) => fail(e, "Could not load"))
const allowed = (t) => (props.mode === "import" ? t.can_import : t.can_export)
const isOther = computed(() => !!props.modelValue && !!types.value && !types.value.some((t) => t.doctype === props.modelValue))

const find = debounce(() => adm("search_doctypes", { txt: search.value }).then((d) => (others.value = d)).catch(fail), 250)
watch(search, find, { immediate: true })
</script>
