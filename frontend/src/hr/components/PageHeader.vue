<template>
	<header class="sticky top-0 z-20 flex items-center gap-3 border-b bg-white px-4 lg:px-6 h-14 shrink-0">
		<router-link v-if="back" :to="back" class="-ml-1 rounded p-1 text-gray-600 hover:bg-gray-100" aria-label="Back">
			<FeatherIcon name="chevron-left" class="h-5 w-5" />
		</router-link>
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<h1 class="truncate text-lg font-semibold">{{ title }}</h1>
				<slot name="badge" />
			</div>
			<div v-if="subtitle" class="truncate text-xs text-gray-500">{{ subtitle }}</div>
		</div>
		<div class="flex items-center gap-2"><slot /></div>
	</header>
</template>

<script setup>
defineProps({ title: String, subtitle: String, back: [String, Object] })
</script>
