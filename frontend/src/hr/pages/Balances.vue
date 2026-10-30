<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="boot.is_hr ? 'Leave balances' : 'Team balances'"
			subtitle="Days left per person, per leave type — straight from the leave ledger">
			<Button v-if="boot.is_hr" :link="'/app/query-report/Employee Leave Balance'" icon-left="external-link" label="Full report" variant="ghost" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<div class="flex flex-wrap items-end gap-3">
				<div class="relative w-full sm:w-72">
					<FeatherIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
					<input v-model="search" type="search" class="form-input w-full pl-8" placeholder="Search people" />
				</div>
				<div v-if="boot.is_hr" class="w-full sm:w-64">
					<LinkField v-model="department" doctype="Department" placeholder="All departments" />
				</div>
			</div>

			<section class="rounded-lg border bg-white">
				<div v-if="loading" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<Empty v-else-if="!rows.length" icon="users">
					Nobody to show{{ search ? ` matching “${search}”` : "" }}.
				</Empty>
				<template v-else>
					<!-- Desktop: person × leave type -->
					<div class="hidden md:block overflow-x-auto">
						<table class="w-full text-sm tabular">
							<thead class="bg-gray-50">
								<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
									<th class="sticky left-0 bg-gray-50 px-4 py-2 font-medium">Employee</th>
									<th v-for="t in data.types" :key="t" class="px-3 py-2 text-right font-medium">{{ t }}</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="r in rows" :key="r.employee" class="border-t hover:bg-gray-50">
									<td class="sticky left-0 bg-white px-4 py-2">
										<component :is="boot.is_hr ? 'router-link' : 'div'" :to="`/people/${r.employee}`" class="block">
											<div class="font-medium">{{ r.employee_name }}</div>
											<div class="text-xs text-gray-500">{{ r.department || r.employee }}</div>
										</component>
									</td>
									<td v-for="t in data.types" :key="t" class="px-3 py-2 text-right">
										<template v-if="r.balances[t]">
											<div class="font-medium" :class="r.balances[t].remaining_leaves <= 0 ? 'text-red-600' : ''">
												{{ n(r.balances[t].remaining_leaves) }}<span class="font-normal text-gray-400"> / {{ n(r.balances[t].total_leaves) }}</span>
											</div>
											<div class="text-xs text-gray-500">
												{{ n(r.balances[t].leaves_taken) }} taken<template v-if="r.balances[t].leaves_pending_approval">
													· {{ n(r.balances[t].leaves_pending_approval) }} pending</template>
											</div>
										</template>
										<span v-else class="text-gray-300">—</span>
									</td>
								</tr>
							</tbody>
						</table>
					</div>

					<!-- Mobile: a card per person -->
					<ul class="md:hidden divide-y">
						<li v-for="r in rows" :key="r.employee" class="px-4 py-3">
							<div class="font-medium">{{ r.employee_name }}</div>
							<div v-if="!Object.keys(r.balances).length" class="text-sm text-amber-700">No allocation — balance is 0</div>
							<div v-for="(b, t) in r.balances" :key="t" class="mt-1 flex justify-between text-sm tabular">
								<span class="text-gray-600">{{ t }}</span>
								<span><b :class="b.remaining_leaves <= 0 ? 'text-red-600' : ''">{{ n(b.remaining_leaves) }}</b>
									<span class="text-gray-400"> / {{ n(b.total_leaves) }}</span></span>
							</div>
						</li>
					</ul>
				</template>
			</section>
			<p class="text-xs text-gray-500">
				Remaining / allocated for the current period. A blank cell means no allocation for that type —
				assign the leave policy under <router-link v-if="boot.is_hr" to="/leave" class="underline">Leave</router-link><span v-else>Leave</span>.
			</p>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { LoadingIndicator } from "frappe-ui"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import { hr, fail } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Empty from "../components/Empty.vue"

const data = ref({ types: [], rows: [] })
const loading = ref(true)
const search = ref("")
const department = ref("")

const n = (v) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })
const rows = computed(() => {
	const q = search.value.trim().toLowerCase()
	return data.value.rows.filter((r) => !q || r.employee_name.toLowerCase().includes(q) || r.employee.toLowerCase().includes(q))
})

async function load() {
	loading.value = true
	try {
		data.value = await hr("get_balances", { department: department.value || undefined })
	} catch (e) {
		fail(e, "Could not load balances")
	} finally {
		loading.value = false
	}
}
watch(department, load)
load()
</script>
