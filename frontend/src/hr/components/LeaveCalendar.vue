<template>
	<div class="grid gap-4 xl:grid-cols-[1fr_340px]">
		<!-- Month -->
		<section class="min-w-0 rounded-lg border bg-white">
			<header class="flex flex-wrap items-center gap-2 border-b px-4 py-3">
				<div class="flex items-center gap-1">
					<Button size="sm" icon="chevron-left" aria-label="Previous month" @click="shift(-1)" />
					<Button size="sm" icon="chevron-right" aria-label="Next month" @click="shift(1)" />
					<Button size="sm" label="Today" @click="goToday" />
				</div>
				<h2 class="flex-1 text-base font-semibold">{{ monthLabel }}</h2>
				<select v-model="department" class="form-select h-8 w-48 text-sm" aria-label="Department">
					<option value="">All departments</option>
					<option v-for="d in data?.departments || []" :key="d" :value="d">{{ d }}</option>
				</select>
				<LoadingIndicator v-if="loading" class="h-4 w-4 text-gray-500" />
			</header>

			<!-- Desktop: the month grid -->
			<div class="hidden md:block">
				<div class="grid grid-cols-7 border-b text-center text-xs font-medium uppercase tracking-wide text-gray-500">
					<div v-for="w in WEEKDAYS" :key="w" class="py-2">{{ w }}</div>
				</div>
				<div class="grid grid-cols-7">
					<button v-for="d in days" :key="d.key" type="button"
						class="min-h-[104px] border-b border-r p-1.5 text-left align-top transition-colors last:border-r-0 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-gray-400"
						:class="[d.inMonth ? '' : 'text-gray-400', d.weekend || d.weeklyOff ? 'bg-gray-50' : 'bg-white',
							d.key === selected ? 'ring-2 ring-inset ring-gray-900' : 'hover:bg-gray-50']"
						@click="selected = d.key">
						<div class="flex items-center justify-between">
							<span class="grid h-6 w-6 place-items-center rounded-full text-xs tabular"
								:class="d.key === todayKey ? 'bg-gray-900 font-semibold text-white' : ''">{{ d.day }}</span>
							<span v-if="d.off.length" class="text-[11px] text-gray-500">{{ d.off.length }} off</span>
						</div>
						<div v-if="d.holiday" class="mt-1 truncate rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800" :title="d.holiday">
							{{ d.holiday }}
						</div>
						<div class="mt-1 space-y-0.5">
							<div v-for="l in d.off.slice(0, CELL_MAX)" :key="l.employee" :title="tip(l, d.key)"
								class="flex items-center gap-1 truncate rounded px-1.5 py-0.5 text-[11px]"
								:class="l.pending ? 'border border-dashed border-teal-400 text-teal-800' : 'bg-teal-50 text-teal-900'">
								<span class="truncate">{{ short(l.employee_name) }}</span>
								<span v-if="isHalf(l, d.key)" class="shrink-0 font-semibold">½</span>
							</div>
							<div v-if="d.off.length > CELL_MAX" class="px-1.5 text-[11px] text-gray-500">+{{ d.off.length - CELL_MAX }} more</div>
						</div>
					</button>
				</div>
				<p class="flex flex-wrap items-center gap-4 px-4 py-2 text-xs text-gray-500">
					<span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded bg-teal-50 ring-1 ring-teal-200" /> Approved</span>
					<span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded border border-dashed border-teal-400" /> Waiting for approval</span>
					<span class="flex items-center gap-1.5"><b class="text-gray-700">½</b> Half day</span>
					<span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded bg-amber-50 ring-1 ring-amber-200" /> Holiday</span>
				</p>
			</div>

			<!-- Phone: the days that have something on them -->
			<div class="divide-y md:hidden">
				<button v-for="d in busyDays" :key="d.key" type="button" class="block w-full px-4 py-3 text-left"
					:class="d.key === selected ? 'bg-gray-50' : ''" @click="selected = d.key">
					<div class="flex items-center gap-2 text-sm">
						<span class="font-medium" :class="d.key === todayKey ? 'text-gray-900' : 'text-gray-700'">{{ longDate(d.key) }}</span>
						<span v-if="d.key === todayKey" class="rounded bg-gray-900 px-1.5 text-[11px] text-white">Today</span>
						<span v-if="d.holiday" class="truncate rounded bg-amber-50 px-1.5 text-[11px] text-amber-800">{{ d.holiday }}</span>
					</div>
					<div v-if="d.off.length" class="mt-1.5 flex flex-wrap gap-1">
						<span v-for="l in d.off" :key="l.employee" class="rounded px-1.5 py-0.5 text-xs"
							:class="l.pending ? 'border border-dashed border-teal-400 text-teal-800' : 'bg-teal-50 text-teal-900'">
							{{ l.employee_name }}<b v-if="isHalf(l, d.key)"> ½</b>
						</span>
					</div>
				</button>
				<Empty v-if="data && !busyDays.length" icon="sun">Nobody is off this month.</Empty>
			</div>
		</section>

		<!-- The picked day -->
		<aside class="space-y-4">
			<section class="rounded-lg border bg-white">
				<header class="border-b px-4 py-3">
					<h3 class="font-semibold">{{ selected === todayKey ? "Today" : longDate(selected) }}</h3>
					<p v-if="selectedDay?.holiday" class="text-sm text-amber-800">{{ selectedDay.holiday }}</p>
					<p v-else-if="selectedDay?.weekend || selectedDay?.weeklyOff" class="text-sm text-gray-500">Weekend</p>
				</header>
				<div class="px-4 py-3">
					<div class="text-xs font-medium uppercase tracking-wide text-gray-500">Off · {{ selectedOff.length }}</div>
					<p v-if="!selectedOff.length" class="mt-1 text-sm text-gray-500">Nobody{{ department ? " in " + department : "" }}.</p>
					<ul class="mt-2 space-y-2">
						<li v-for="l in selectedOff" :key="l.employee" class="flex items-center gap-2.5">
							<Avatar :name="l.employee_name" :image="l.image" />
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium">{{ l.employee_name }}<span v-if="isHalf(l, selected)" class="font-normal text-gray-500"> · half day</span></div>
								<div class="truncate text-xs text-gray-500">
									{{ l.leave_type || "On leave" }}<template v-if="l.pending"> · waiting for approval</template>
									· {{ range(l) }}
								</div>
							</div>
							<router-link v-if="l.name && boot.is_hr" :to="`/records/leave-applications/${encodeURIComponent(l.name)}`"
								class="text-xs text-blue-700 hover:underline">Open</router-link>
						</li>
					</ul>
				</div>
				<div class="border-t px-4 py-3">
					<button type="button" class="flex w-full items-center justify-between text-left" @click="showAvailable = !showAvailable">
						<span class="text-xs font-medium uppercase tracking-wide text-gray-500">Available · {{ available.length }}</span>
						<FeatherIcon :name="showAvailable ? 'chevron-up' : 'chevron-down'" class="h-4 w-4 text-gray-400" />
					</button>
					<ul v-if="showAvailable" class="mt-2 max-h-80 space-y-1.5 overflow-y-auto">
						<li v-for="p in available" :key="p.name" class="flex items-center gap-2.5 text-sm">
							<Avatar :name="p.employee_name" :image="p.image" small />
							<span class="min-w-0 flex-1 truncate">{{ p.employee_name }}</span>
							<span class="truncate text-xs text-gray-400">{{ p.department?.replace(/ - [^-]+$/, "") }}</span>
						</li>
					</ul>
				</div>
			</section>

			<section v-if="upcoming.length" class="rounded-lg border bg-white">
				<h3 class="border-b px-4 py-3 font-semibold">Coming up</h3>
				<ul class="divide-y">
					<li v-for="l in upcoming" :key="l.employee + l.from_date" class="flex items-center gap-2.5 px-4 py-2">
						<Avatar :name="l.employee_name" :image="l.image" small />
						<div class="min-w-0 flex-1">
							<div class="truncate text-sm">{{ l.employee_name }}</div>
							<div class="truncate text-xs text-gray-500">{{ range(l) }}<template v-if="l.pending"> · waiting for approval</template></div>
						</div>
					</li>
				</ul>
			</section>
		</aside>
	</div>
</template>

<script setup>
import { computed, h, ref, watch } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import { boot } from "@/boot"
import { fail } from "../api"
import Empty from "./Empty.vue"

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const CELL_MAX = 3

const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const parse = (s) => { const [y, m, d] = String(s).slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d) }
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)

const todayKey = ymd(new Date())
const month = ref(new Date(new Date().getFullYear(), new Date().getMonth(), 1))
const department = ref("")
const selected = ref(todayKey)
const showAvailable = ref(false)
const data = ref(null)
const loading = ref(false)

const gridStart = computed(() => addDays(month.value, -((month.value.getDay() + 6) % 7)))
const monthLabel = computed(() => month.value.toLocaleDateString(undefined, { month: "long", year: "numeric" }))

async function load() {
	loading.value = true
	try {
		data.value = await call("erp_overrides.api.leave_calendar.get_calendar", {
			start: ymd(gridStart.value), end: ymd(addDays(gridStart.value, 41)), department: department.value || undefined,
		})
	} catch (e) {
		fail(e, "Could not load the calendar")
	} finally {
		loading.value = false
	}
}
watch([month, department], load, { immediate: true })

function shift(n) {
	month.value = new Date(month.value.getFullYear(), month.value.getMonth() + n, 1)
	selected.value = ymd(month.value)
}
function goToday() {
	month.value = new Date(new Date().getFullYear(), new Date().getMonth(), 1)
	selected.value = todayKey
}

const holidays = computed(() => Object.fromEntries((data.value?.holidays || []).map((x) => [String(x.date).slice(0, 10), x])))
const offOn = (key) => (data.value?.leave || []).filter((l) => String(l.from_date) <= key && key <= String(l.to_date))

const days = computed(() => Array.from({ length: 42 }, (_, i) => {
	const date = addDays(gridStart.value, i)
	const key = ymd(date)
	const hol = holidays.value[key]
	return {
		key, day: date.getDate(), inMonth: date.getMonth() === month.value.getMonth(),
		weekend: !hol && [0, 6].includes(date.getDay()), weeklyOff: !!hol?.weekly_off,
		holiday: hol && !hol.weekly_off ? hol.description || "Holiday" : "",
		off: offOn(key),
	}
}))
const busyDays = computed(() => days.value.filter((d) => d.inMonth && (d.off.length || d.holiday)))
const selectedDay = computed(() => days.value.find((d) => d.key === selected.value))
const selectedOff = computed(() => selectedDay.value?.off || offOn(selected.value))
const available = computed(() => {
	const off = new Set(selectedOff.value.filter((l) => !isHalf(l, selected.value)).map((l) => l.employee))
	return (data.value?.people || []).filter((p) => !off.has(p.name))
})
const upcoming = computed(() => (data.value?.leave || [])
	.filter((l) => String(l.from_date) > selected.value).slice(0, 8))

const isHalf = (l, key) => !!l.half_day && String(l.half_day_date || l.from_date) === key
const short = (name) => { const p = String(name || "").split(" "); return p.length > 1 ? `${p[0]} ${p[p.length - 1][0]}.` : p[0] }
const longDate = (key) => parse(key).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })
const fmt = (s) => parse(s).toLocaleDateString(undefined, { day: "numeric", month: "short" })
const range = (l) => (l.from_date === l.to_date ? fmt(l.from_date) : `${fmt(l.from_date)} – ${fmt(l.to_date)}`)
const tip = (l, key) => `${l.employee_name} · ${l.leave_type || "On leave"}${isHalf(l, key) ? " (half day)" : ""}${l.pending ? " · waiting for approval" : ""} · ${range(l)}`

const Avatar = (props) => h("div", {
	class: ["grid shrink-0 place-items-center overflow-hidden rounded-full bg-gray-200 font-medium text-gray-700",
		props.small ? "h-6 w-6 text-[10px]" : "h-8 w-8 text-xs"],
}, props.image ? [h("img", { src: props.image, class: "h-full w-full object-cover", alt: "" })]
	: (props.name || "").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase())
Avatar.props = ["name", "image", "small"]
</script>
