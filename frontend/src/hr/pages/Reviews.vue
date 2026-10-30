<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Bi-weekly reviews" subtitle="Check-ins between each employee and their manager; reminders go out by themselves">
			<Button label="Open due reviews now" icon-left="play" :loading="opening" @click="openNow" />
		</PageHeader>

		<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-[1600px] space-y-4 p-4 lg:p-6">
			<!-- The last six weeks of windows -->
			<section class="grid grid-cols-2 gap-3 md:grid-cols-4">
				<button v-for="t in tiles" :key="t.key" type="button" class="rounded-lg border bg-white px-4 py-3 text-left hover:border-gray-400"
					:class="filter === t.key ? 'border-gray-900 ring-1 ring-gray-900' : ''" @click="filter = filter === t.key ? '' : t.key">
					<div class="text-xs text-gray-500">{{ t.label }}</div>
					<div class="text-2xl font-semibold tabular" :class="t.key === 'overdue' && t.value ? 'text-red-700' : ''">{{ t.value }}</div>
				</button>
			</section>

			<div class="grid gap-4 xl:grid-cols-[1fr_380px]">
				<section class="min-w-0 rounded-lg border bg-white">
					<header class="flex flex-wrap items-center gap-2 border-b px-4 py-3">
						<h2 class="flex-1 font-semibold">Reviews opened in the last six weeks</h2>
						<select v-model="manager" class="form-select h-8 w-56 text-sm" aria-label="Manager">
							<option value="">All managers</option>
							<option v-for="m in data.by_manager" :key="m.manager" :value="m.manager">{{ m.manager_name }}</option>
						</select>
					</header>
					<Empty v-if="!rows.length" icon="clipboard">{{ data.schedules.length ? "No reviews here." : "Set up a schedule (right) and reviews open at the end of each period." }}</Empty>
					<div v-else class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
								<tr><th class="px-4 py-2 font-medium">Employee</th><th class="px-2 py-2 font-medium">Manager</th>
									<th class="px-2 py-2 font-medium">Period</th><th class="px-2 py-2 font-medium">Due</th><th class="px-4 py-2 font-medium">Status</th></tr>
							</thead>
							<tbody>
								<tr v-for="r in rows" :key="r.name" class="cursor-pointer border-t hover:bg-gray-50" @click="$router.push(`/reviews/${encodeURIComponent(r.name)}`)">
									<td class="px-4 py-2 font-medium">{{ r.employee_name }}</td>
									<td class="px-2 py-2 text-gray-600">{{ r.manager_name || "—" }}</td>
									<td class="px-2 py-2 whitespace-nowrap text-gray-600">{{ date(r.period_start) }} – {{ date(r.period_end) }}</td>
									<td class="px-2 py-2 whitespace-nowrap" :class="r.overdue && r.status !== 'Completed' ? 'text-red-700' : 'text-gray-600'">{{ date(r.due_on) }}</td>
									<td class="px-4 py-2"><span class="rounded px-1.5 py-0.5 text-xs" :class="theme(r)">{{ label(r) }}</span>
										<span v-if="r.appraisal" class="ml-1 text-xs text-gray-500">· in appraisal</span></td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<aside class="space-y-4">
					<section class="rounded-lg border bg-white">
						<header class="flex items-center justify-between border-b px-4 py-3">
							<h3 class="font-semibold">Schedules</h3>
							<Button size="sm" icon-left="plus" label="New" @click="$router.push('/review-schedules/new')" />
						</header>
						<p v-if="!data.schedules.length" class="px-4 py-3 text-sm text-gray-500">None yet. A schedule says who is reviewed, how often, and with which form.</p>
						<router-link v-for="s in data.schedules" :key="s.name" :to="`/review-schedules/${encodeURIComponent(s.name)}`"
							class="block border-t px-4 py-2.5 text-sm first-of-type:border-t-0 hover:bg-gray-50">
							<div class="flex items-center gap-2"><span class="flex-1 truncate font-medium">{{ s.name }}</span>
								<span class="text-xs" :class="s.active ? 'text-green-700' : 'text-gray-400'">{{ s.active ? "Active" : "Paused" }}</span></div>
							<div class="truncate text-xs text-gray-500">{{ s.frequency }} · {{ s.review_form }}</div>
							<div v-if="s.skipped" class="truncate text-xs text-amber-700">No manager: {{ s.skipped }}</div>
						</router-link>
					</section>
					<section class="rounded-lg border bg-white">
						<header class="flex items-center justify-between border-b px-4 py-3">
							<h3 class="font-semibold">Review forms</h3>
							<Button size="sm" icon-left="plus" label="New" @click="$router.push('/review-forms/new')" />
						</header>
						<router-link v-for="f in data.forms" :key="f.name" :to="`/review-forms/${encodeURIComponent(f.name)}`"
							class="flex items-center gap-2 border-t px-4 py-2.5 text-sm first-of-type:border-t-0 hover:bg-gray-50">
							<span class="flex-1 truncate font-medium">{{ f.name }}</span>
							<span class="text-xs" :class="f.active ? 'text-green-700' : 'text-gray-400'">{{ f.active ? "Active" : "Retired" }}</span>
						</router-link>
					</section>
					<section class="rounded-lg border bg-white px-4 py-3 text-sm text-gray-600">
						<h3 class="mb-1 font-semibold text-gray-900">Reminders</h3>
						<p>06:00 daily: reviews open the day after a period ends (email + bell to employee and manager); two days before the due date whoever hasn't done their part is reminded; late ones are marked overdue. Mondays 07:00: the overdue list goes to HR.</p>
					</section>
				</aside>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import { date } from "@/utils/format"
import { fail, ok } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Empty from "../components/Empty.vue"

const M = "erp_overrides.api.reviews"
const data = ref(null)
const filter = ref("")
const manager = ref("")
const opening = ref(false)

async function load() {
	try {
		data.value = await call(`${M}.get_reviews`)
	} catch (e) {
		fail(e)
	}
}
load()

const tiles = computed(() => [
	{ key: "open", label: "Waiting for the employee", value: data.value.totals.open },
	{ key: "self_done", label: "Waiting for the manager", value: data.value.totals.self_done },
	{ key: "completed", label: "Completed", value: data.value.totals.completed },
	{ key: "overdue", label: "Overdue", value: data.value.totals.overdue },
])
const rows = computed(() => (data.value?.rows || []).filter((r) =>
	(!manager.value || r.manager === manager.value) &&
	(!filter.value || (filter.value === "overdue" ? r.overdue && r.status !== "Completed"
		: r.status === { open: "Open", self_done: "Self done", completed: "Completed" }[filter.value]))))

const label = (r) => ({ Open: "Waiting for the employee", "Self done": "Waiting for the manager", Completed: "Completed" }[r.status]
	+ (r.overdue && r.status !== "Completed" ? " · overdue" : ""))
const theme = (r) => (r.status === "Completed" ? "bg-green-50 text-green-800" : r.overdue ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-900")

async function openNow() {
	opening.value = true
	try {
		const opened = await call(`${M}.open_now`)
		ok(opened.length ? `${opened.length} review${opened.length === 1 ? "" : "s"} opened` : "Nothing due to open today")
		await load()
	} catch (e) {
		fail(e)
	} finally {
		opening.value = false
	}
}
</script>
