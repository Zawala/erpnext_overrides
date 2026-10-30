<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Reports" subtitle="Every report exports to Excel, CSV or PDF with the filters you applied — and can be scheduled to email itself" />

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-6">
			<div v-if="!groups" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<section>
				<h2 class="mb-2 text-xs font-medium uppercase tracking-wide text-green-700">In this app</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
					<router-link to="/pay-report" class="rounded-lg border border-green-200 bg-white p-4 transition-colors hover:border-gray-400">
						<div class="font-medium">Pay report</div>
						<div class="mt-1 text-sm text-gray-500">Each person's earnings, every deduction (pension, PAYE…) and net pay over any period, slip by slip, with CSV</div>
					</router-link>
				</div>
			</section>
			<section v-for="g in groups || []" :key="g.group">
				<h2 class="mb-2 text-xs font-medium uppercase tracking-wide" :class="g.group === 'Custom reports' ? 'text-green-700' : 'text-gray-500'">{{ g.group }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
					<a v-for="r in g.reports" :key="r.name" :href="r.url" target="_blank"
						class="rounded-lg border bg-white p-4 transition-colors hover:border-gray-400"
						:class="g.group === 'Custom reports' ? 'border-green-200' : ''">
						<div class="flex items-start justify-between gap-2">
							<div class="font-medium">{{ r.name }}</div>
							<FeatherIcon name="external-link" class="h-4 w-4 shrink-0 text-gray-400" />
						</div>
						<div class="mt-1 text-sm text-gray-500">{{ r.description }}</div>
					</a>
				</div>
			</section>
			<section>
				<h2 class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Records</h2>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
					<router-link v-for="(r, slug) in records" :key="slug" :to="`/records/${slug}`"
						class="flex items-center gap-2 rounded-lg border bg-white p-3 text-sm hover:border-gray-400">
						<FeatherIcon :name="r.icon" class="h-4 w-4 text-gray-500" />{{ r.label }}
					</router-link>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { LoadingIndicator } from "frappe-ui"
import { hr, fail } from "../api"
import { records } from "../records"
import PageHeader from "../components/PageHeader.vue"

const groups = ref(null)
hr("get_reports").then((g) => (groups.value = g.filter((x) => x.reports.length))).catch((e) => fail(e, "Could not load reports"))
</script>
