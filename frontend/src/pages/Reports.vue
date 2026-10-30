<template>
	<div class="h-full overflow-y-auto">
		<header class="sticky top-0 z-10 flex h-14 items-center gap-3 border-b bg-white px-4 lg:px-6">
			<FeatherIcon name="bar-chart-2" class="h-5 w-5 text-gray-500" />
			<h1 class="flex-1 truncate text-lg font-semibold">Reports</h1>
		</header>
		<div class="mx-auto w-full max-w-[1600px] space-y-6 p-4 lg:p-6">
			<MySales hide-reports v-if="can('Quotation') || can('Sales Order') || can('Sales Invoice')" />
			<div>
				<h2 class="text-base font-semibold">Full reports</h2>
				<p class="mb-3 text-sm text-gray-500">Open in desk. Each one filters, exports to Excel, CSV or PDF, and can email itself on a schedule.</p>
				<ReportsGrid :groups="groups" />
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { toast } from "frappe-ui"
import MySales from "@/components/MySales.vue"
import ReportsGrid from "@/components/ReportsGrid.vue"
import { can } from "@/doctypes"
import { api, errorMessages } from "@/utils/api"

const groups = ref(null)
api("get_reports").then((g) => (groups.value = g)).catch((e) => {
	groups.value = []
	toast({ title: "Could not load reports", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600" })
})
</script>
