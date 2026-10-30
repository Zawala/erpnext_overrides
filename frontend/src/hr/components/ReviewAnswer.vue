<template>
	<!-- One answer to a review question, by kind: Rating 1–5, Yes / No, Choice or Text -->
	<div v-if="kind === 'Rating'" class="flex flex-wrap items-center gap-1.5" role="radiogroup">
		<button v-for="n in 5" :key="n" type="button" :disabled="readonly" role="radio" :aria-checked="String(modelValue) === String(n)"
			class="h-9 w-9 rounded-md border text-sm font-medium tabular transition-colors"
			:class="String(modelValue) === String(n) ? 'border-gray-900 bg-gray-900 text-white' : readonly ? 'text-gray-400' : 'hover:border-gray-500'"
			@click="emit('update:modelValue', String(n))">{{ n }}</button>
		<span v-if="readonly && !modelValue" class="text-sm text-gray-400">—</span>
	</div>
	<div v-else-if="kind === 'Yes / No'" class="flex gap-1.5">
		<button v-for="v in ['Yes', 'No']" :key="v" type="button" :disabled="readonly"
			class="rounded-md border px-3 py-1.5 text-sm"
			:class="modelValue === v ? 'border-gray-900 bg-gray-900 text-white' : readonly ? 'text-gray-400' : 'hover:border-gray-500'"
			@click="emit('update:modelValue', v)">{{ v }}</button>
	</div>
	<select v-else-if="kind === 'Choice'" :value="modelValue || ''" :disabled="readonly" class="form-select w-full"
		@change="emit('update:modelValue', $event.target.value)">
		<option value="">—</option>
		<option v-for="o in choices" :key="o" :value="o">{{ o }}</option>
	</select>
	<p v-else-if="readonly" class="whitespace-pre-line text-sm" :class="modelValue ? 'text-gray-800' : 'text-gray-400'">{{ modelValue || "—" }}</p>
	<textarea v-else :value="modelValue || ''" rows="3" class="form-textarea w-full"
		@input="emit('update:modelValue', $event.target.value)" />
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({ kind: String, options: String, modelValue: [String, Number], readonly: Boolean })
const emit = defineEmits(["update:modelValue"])
const choices = computed(() => (props.options || "").split("\n").map((s) => s.trim()).filter(Boolean))
</script>
