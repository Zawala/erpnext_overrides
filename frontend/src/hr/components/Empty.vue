<template>
	<div class="px-4 py-10 text-center text-gray-500">
		<FeatherIcon v-if="icon" :name="icon" class="mx-auto mb-2 h-6 w-6 text-gray-300" />
		<slot />
	</div>
</template>

<script setup>
defineProps({ icon: String })
</script>
