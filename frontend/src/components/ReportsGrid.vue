<template>
	<div class="space-y-6">
		<div class="relative max-w-xl">
			<FeatherIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
			<input v-model="q" type="search" class="form-input w-full pl-8" placeholder="Find a report — “ledger”, “VAT”, “overdue”…" />
		</div>
		<div v-if="!groups" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<p v-else-if="!shown.length" class="text-sm text-gray-500">No report matches “{{ q }}”.</p>
		<section v-for="g in shown" :key="g.group">
			<h2 class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">{{ g.group }}</h2>
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
				<a v-for="r in g.reports" :key="r.name" :href="r.url" target="_blank" rel="noopener"
					class="rounded-lg border bg-white p-4 transition-colors hover:border-gray-400">
					<div class="flex items-start justify-between gap-2">
						<div class="font-medium">{{ r.name }}</div>
						<FeatherIcon name="external-link" class="h-4 w-4 shrink-0 text-gray-400" />
					</div>
					<div v-if="r.description" class="mt-1 text-sm text-gray-500">{{ r.description }}</div>
				</a>
			</div>
		</section>
	</div>
</template>

<script setup>
/** Grouped desk report links ([{ group, reports: [{ name, description, url }] }]) with a search box. */
import { computed, ref } from "vue"
import { FeatherIcon, LoadingIndicator } from "frappe-ui"

const props = defineProps({ groups: Array })
const q = ref("")
const shown = computed(() => {
	const t = q.value.trim().toLowerCase()
	return (props.groups || [])
		.map((g) => ({ ...g, reports: g.reports.filter((r) => !t || `${r.name} ${r.description} ${g.group}`.toLowerCase().includes(t)) }))
		.filter((g) => g.reports.length)
})
</script>
