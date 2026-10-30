<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Data" subtitle="Bring records in from a spreadsheet, or take them out to one" />

		<div class="mx-auto w-full max-w-[1200px] space-y-4 p-4 lg:p-6">
			<div class="grid gap-3 sm:grid-cols-2">
				<router-link to="/data/import" class="rounded-lg border bg-white p-5 hover:border-gray-400">
					<FeatherIcon name="upload-cloud" class="h-6 w-6 text-gray-700" />
					<div class="mt-2 text-base font-semibold">Import data</div>
					<p class="mt-1 text-sm text-gray-600">Add new customers, suppliers, items, employees and more, or update ones you have, from an Excel or CSV file.
						You check everything before it's saved.</p>
				</router-link>
				<router-link to="/data/export" class="rounded-lg border bg-white p-5 hover:border-gray-400">
					<FeatherIcon name="download-cloud" class="h-6 w-6 text-gray-700" />
					<div class="mt-2 text-base font-semibold">Export data</div>
					<p class="mt-1 text-sm text-gray-600">Download records to work on in Excel, share, or edit and import back to update them.</p>
				</router-link>
			</div>

			<section class="rounded-lg border bg-white">
				<h3 class="border-b px-4 py-3 font-semibold">Import history</h3>
				<div v-if="!imports" class="p-6 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<p v-else-if="!imports.length" class="px-4 py-6 text-sm text-gray-500">No imports yet.</p>
				<ul v-else class="divide-y">
					<li v-for="i in imports" :key="i.name">
						<router-link :to="`/data/import/${encodeURIComponent(i.name)}`" class="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm hover:bg-gray-50">
							<span class="rounded px-1.5 py-0.5 text-xs" :class="THEME[i.status]">{{ LABEL[i.status] || i.status }}</span>
							<span class="min-w-0 flex-1">
								<span class="font-medium">{{ i.doctype }}</span>
								<span class="text-gray-500"> · {{ i.import_type === "Update Existing Records" ? "update" : "new" }} · {{ i.filename || "no file" }}</span>
							</span>
							<span class="tabular text-gray-600">
								<template v-if="i.succeeded || i.failed">{{ i.succeeded }} saved<template v-if="i.failed">, <span class="text-red-700">{{ i.failed }} not</span></template></template>
								<template v-else-if="i.records">{{ i.records }} records</template>
							</span>
							<span class="w-full text-xs text-gray-500 sm:w-auto">{{ i.by }} · {{ relative(i.when) }}</span>
						</router-link>
					</li>
				</ul>
			</section>
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { FeatherIcon, LoadingIndicator } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import { relative } from "@/utils/format"
import { adm, fail } from "../api"

const LABEL = { Pending: "Not run yet", "In Progress": "Running", Success: "Done", "Partial Success": "Partly done", Error: "Failed", "Timed Out": "Timed out" }
const THEME = {
	Pending: "bg-gray-100 text-gray-600", "In Progress": "bg-blue-50 text-blue-800", Success: "bg-green-50 text-green-800",
	"Partial Success": "bg-amber-50 text-amber-900", Error: "bg-red-50 text-red-800", "Timed Out": "bg-red-50 text-red-800",
}

const imports = ref(null)
adm("get_recent_imports").then((d) => (imports.value = d)).catch((e) => fail(e, "Could not load"))
</script>
