<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Reports" subtitle="Every accounts report you can open — each exports to Excel, CSV or PDF and can email itself on a schedule" />
		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6">
			<ReportsGrid :groups="groups" />
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import PageHeader from "@/hr/components/PageHeader.vue"
import ReportsGrid from "@/components/ReportsGrid.vue"
import { acc, fail } from "../api"

const groups = ref(null)
acc("get_reports").then((g) => (groups.value = g)).catch((e) => {
	groups.value = []
	fail(e, "Could not load reports")
})
</script>
