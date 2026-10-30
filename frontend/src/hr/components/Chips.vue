<template>
	<div class="flex gap-1.5 overflow-x-auto hide-scrollbar">
		<button
			v-for="o in options"
			:key="o.value ?? o"
			class="shrink-0 rounded-full border px-3 py-1 text-sm transition-colors"
			:class="(o.value ?? o) === modelValue ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'"
			@click="$emit('update:modelValue', o.value ?? o)"
		>
			{{ o.label ?? o }}<span v-if="o.count" class="ml-1.5 opacity-70 tabular">{{ o.count }}</span>
		</button>
	</div>
</template>

<script setup>
defineProps({ options: Array, modelValue: [String, Number] })
defineEmits(["update:modelValue"])
</script>
