<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Employees" :subtitle="`${rows.length} ${status === 'All' ? '' : status.toLowerCase()} employees`">
			<Button v-if="can('Employee', 'create')" :link="`${deskUrl('Employee')}/new`" icon-left="plus" label="New employee" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<div class="flex flex-wrap items-center gap-3">
				<div class="relative w-full sm:w-72">
					<FeatherIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
					<input v-model="search" type="search" class="form-input w-full pl-8" placeholder="Search name, ID, designation" />
				</div>
				<div class="w-full sm:w-60"><LinkField v-model="department" doctype="Department" placeholder="All departments" /></div>
				<Chips v-model="status" :options="['Active', 'Suspended', 'Left', 'All']" />
			</div>

			<section class="rounded-lg border bg-white">
				<div v-if="loading" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<Empty v-else-if="!shown.length" icon="users">Nobody matches.</Empty>
				<template v-else>
					<table class="hidden md:table w-full text-sm">
						<thead class="bg-gray-50">
							<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
								<th class="px-4 py-2 font-medium">Employee</th>
								<th class="px-3 py-2 font-medium">Department</th>
								<th class="px-3 py-2 font-medium">Designation</th>
								<th class="px-3 py-2 font-medium">Reports to</th>
								<th class="px-3 py-2 font-medium">Login</th>
								<th class="px-4 py-2 font-medium">Status</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="r in shown" :key="r.name" class="cursor-pointer border-t hover:bg-gray-50" @click="$router.push(`/people/${r.name}`)">
								<td class="px-4 py-2.5"><div class="font-medium">{{ r.employee_name }}</div><div class="text-xs text-gray-500">{{ r.name }}</div></td>
								<td class="px-3 py-2.5 text-gray-700">{{ r.department || "—" }}</td>
								<td class="px-3 py-2.5 text-gray-700">{{ r.designation || "—" }}</td>
								<td class="px-3 py-2.5 text-gray-700">{{ names[r.reports_to] || (r.reports_to ? r.reports_to : "—") }}</td>
								<td class="px-3 py-2.5">
									<span v-if="r.user_id" class="text-gray-700">{{ r.user_id }}</span>
									<span v-else class="text-red-600">No User ID</span>
								</td>
								<td class="px-4 py-2.5"><StatusBadge :status="r.status" size="sm" /></td>
							</tr>
						</tbody>
					</table>
					<ul class="md:hidden divide-y">
						<li v-for="r in shown" :key="r.name">
							<router-link :to="`/people/${r.name}`" class="flex items-center justify-between gap-3 px-4 py-3">
								<div class="min-w-0">
									<div class="truncate font-medium">{{ r.employee_name }}</div>
									<div class="truncate text-sm text-gray-500">{{ [r.designation, r.department].filter(Boolean).join(" · ") || r.name }}</div>
								</div>
								<StatusBadge :status="r.status" size="sm" />
							</router-link>
						</li>
					</ul>
				</template>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { can, deskUrl, fail } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import Empty from "../components/Empty.vue"

const rows = ref([])
const loading = ref(true)
const search = ref("")
const department = ref("")
const status = ref("Active")

const names = computed(() => Object.fromEntries(rows.value.map((r) => [r.name, r.employee_name])))
const shown = computed(() => {
	const q = search.value.trim().toLowerCase()
	return rows.value.filter((r) =>
		!q || [r.employee_name, r.name, r.designation, r.user_id].some((v) => (v || "").toLowerCase().includes(q)))
})

async function load() {
	loading.value = true
	try {
		const filters = {}
		if (status.value !== "All") filters.status = status.value
		if (department.value) filters.department = department.value
		rows.value = await call("frappe.client.get_list", {
			doctype: "Employee",
			fields: ["name", "employee_name", "department", "designation", "reports_to", "user_id", "status"],
			filters,
			order_by: "employee_name asc",
			limit_page_length: 0,
		})
	} catch (e) {
		fail(e, "Could not load employees")
	} finally {
		loading.value = false
	}
}
watch([status, department], load)
load()
</script>
