<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Attendance" subtitle="Mark a whole group for a day in one screen">
			<Button icon-left="list" label="Requests" @click="$router.push('/records/attendance-requests')" />
			<Button class="hidden sm:inline-flex" :link="'/app/query-report/Monthly Attendance Sheet'" icon-left="external-link"
				label="Monthly sheet" variant="ghost" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<section class="rounded-lg border bg-white">
				<div class="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
					<label><span class="mb-1.5 block text-sm text-gray-600">Date</span>
						<input v-model="day" type="date" class="form-input w-full" :max="today()" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Department</span>
						<LinkField v-model="department" doctype="Department" placeholder="All departments" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Branch</span>
						<LinkField v-model="branch" doctype="Branch" placeholder="All branches" /></label>
				</div>
			</section>

			<div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px] items-start">
				<section class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<label class="flex items-center gap-2 font-semibold">
							<input type="checkbox" class="form-checkbox" :checked="allPicked" :disabled="!unmarked.length"
								@change="pickAll($event.target.checked)" />
							Not marked yet <span class="font-normal text-gray-500">· {{ picked.size }} of {{ unmarked.length }} selected</span>
						</label>
					</header>
					<div v-if="loading" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<Empty v-else-if="!unmarked.length" icon="check-circle">Everyone is marked for {{ date(day) }}.</Empty>
					<ul v-else class="grid grid-cols-1 divide-y sm:grid-cols-2 sm:divide-y-0 2xl:grid-cols-3">
						<li v-for="e in unmarked" :key="e.employee">
							<label class="flex cursor-pointer items-center gap-3 px-4 py-2 hover:bg-gray-50">
								<input type="checkbox" class="form-checkbox" :checked="picked.has(e.employee)" @change="toggle(e.employee)" />
								<span class="min-w-0 flex-1 truncate">{{ e.employee_name }}</span>
							</label>
						</li>
					</ul>
				</section>

				<aside class="space-y-4 xl:sticky xl:top-20">
					<section class="rounded-lg border bg-white p-4 space-y-3">
						<h3 class="font-semibold">Mark {{ picked.size }} as</h3>
						<div class="grid grid-cols-2 gap-2">
							<button v-for="s in STATUSES" :key="s" class="rounded border px-3 py-2 text-sm"
								:class="status === s ? 'border-gray-900 bg-gray-900 text-white' : 'hover:bg-gray-50'" @click="status = s">{{ s }}</button>
						</div>
						<div v-if="status === 'On Leave'">
							<span class="mb-1.5 block text-sm text-gray-600">Leave type</span>
							<LinkField v-model="leaveType" doctype="Leave Type" />
							<p class="mt-1 text-xs text-gray-500">Prefer a Leave Application — this only records the day, it doesn't touch the balance.</p>
						</div>
						<label class="flex items-center gap-2 text-sm"><input v-model="late" type="checkbox" class="form-checkbox" /> Late entry</label>
						<label class="flex items-center gap-2 text-sm"><input v-model="early" type="checkbox" class="form-checkbox" /> Early exit</label>
						<Button variant="solid" class="w-full" :label="`Mark ${picked.size} ${status}`" :disabled="!picked.size"
							:loading="saving" @click="mark" />
					</section>

					<section v-if="marked.length" class="rounded-lg border bg-white">
						<h3 class="border-b px-4 py-3 font-semibold">Already marked · {{ marked.length }}</h3>
						<ul class="max-h-80 divide-y overflow-y-auto">
							<li v-for="m in marked" :key="m.employee" class="flex items-center justify-between px-4 py-2 text-sm">
								<span class="truncate">{{ m.employee_name }}</span>
								<StatusBadge :status="m.status" size="sm" />
							</li>
						</ul>
					</section>
				</aside>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { LoadingIndicator } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { date, today } from "@/utils/format"
import { hr, ok, fail } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Empty from "../components/Empty.vue"

const STATUSES = ["Present", "Absent", "Half Day", "Work From Home", "On Leave"]
const day = ref(today())
const department = ref("")
const branch = ref("")
const unmarked = ref([])
const marked = ref([])
const picked = ref(new Set())
const status = ref("Present")
const leaveType = ref("")
const late = ref(false)
const early = ref(false)
const loading = ref(true)
const saving = ref(false)

const allPicked = computed(() => unmarked.value.length > 0 && picked.value.size === unmarked.value.length)
const pickAll = (on) => (picked.value = new Set(on ? unmarked.value.map((e) => e.employee) : []))
function toggle(name) {
	const s = new Set(picked.value)
	s.has(name) ? s.delete(name) : s.add(name)
	picked.value = s
}

async function load() {
	if (!day.value) return
	loading.value = true
	try {
		const r = await hr("get_unmarked", { date: day.value, department: department.value || undefined, branch: branch.value || undefined })
		unmarked.value = r.unmarked
		marked.value = [...r.marked, ...r.half_day_marked.map((m) => ({ ...m, status: "Half Day" }))]
		picked.value = new Set()
	} catch (e) {
		fail(e, "Could not load employees")
	} finally {
		loading.value = false
	}
}

async function mark() {
	saving.value = true
	try {
		const n = await hr("mark_attendance", {
			date: day.value, status: status.value, employees: [...picked.value],
			late_entry: late.value ? 1 : 0, early_exit: early.value ? 1 : 0, leave_type: status.value === "On Leave" ? leaveType.value : undefined,
		})
		ok(`${n} marked ${status.value}`, date(day.value))
		await load()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

watch([day, department, branch], load)
load()
</script>
