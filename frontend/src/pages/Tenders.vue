<template>
	<div class="h-full overflow-y-auto">
		<header class="flex items-center gap-3 border-b bg-white px-4 lg:px-6 h-14 sticky top-0 z-10">
			<FeatherIcon name="briefcase" class="h-5 w-5 text-gray-500" />
			<div class="min-w-0 flex-1 leading-tight">
				<h1 class="truncate text-lg font-semibold">Tenders</h1>
				<div class="truncate text-xs text-gray-500">{{ scrapedLine }}</div>
			</div>
			<Button icon="refresh-cw" :loading="loading" title="Refresh" @click="refresh" />
		</header>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-5">
			<!-- Headline numbers; each one is a shortcut to that view -->
			<div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
				<button v-for="t in tiles" :key="t.label" class="rounded-lg border bg-white p-4 text-left transition-colors hover:border-gray-400"
					:class="t.active ? 'border-gray-900 ring-1 ring-gray-900' : ''" @click="t.apply()">
					<div class="text-sm text-gray-600">{{ t.label }}</div>
					<div class="mt-1 text-2xl font-semibold tabular" :class="t.tone">{{ open ? t.count : "–" }}</div>
					<div class="mt-1 text-xs text-gray-500">{{ t.hint }}</div>
				</button>
			</div>

			<div class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
				<section class="min-w-0 rounded-lg border bg-white">
					<div class="space-y-3 border-b px-4 py-3">
						<div class="relative">
							<FeatherIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
							<input v-model="search" type="search" class="form-input w-full pl-8" placeholder="Search title, entity or reference" />
						</div>
						<div class="flex gap-1.5 overflow-x-auto hide-scrollbar">
							<Chip v-for="c in COUNTRIES" :key="c" :on="country === c" @click="country = c">{{ c }}</Chip>
							<span class="mx-1 w-px shrink-0 bg-gray-200" />
							<Chip v-for="w in WINDOWS" :key="w" :on="view === w" @click="setView(w)">{{ w }}</Chip>
						</div>
						<div v-if="category" class="flex items-center gap-2 text-sm">
							<span class="text-gray-500">Category:</span>
							<span class="truncate font-medium">{{ category }}</span>
							<button class="shrink-0 text-gray-500 hover:text-gray-900" @click="category = ''">
								<FeatherIcon name="x" class="h-4 w-4" />
							</button>
						</div>
						<select v-else class="form-select w-full lg:hidden" @change="category = $event.target.value">
							<option value="">All categories</option>
							<option v-for="c in categoryCounts" :key="c.name" :value="c.name">{{ c.name }} ({{ c.count }})</option>
						</select>
					</div>

					<ul class="divide-y">
						<li v-for="t in visible" :key="t.key" class="px-4 py-3">
							<div class="flex items-start gap-3">
								<span class="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold"
									:class="t.country === 'Zimbabwe' ? 'bg-emerald-50 text-emerald-700' : 'bg-orange-50 text-orange-700'"
									:title="t.country">{{ t.country === "Zimbabwe" ? "ZW" : "ZM" }}</span>
								<div class="min-w-0 flex-1">
									<div class="flex items-start justify-between gap-3">
										<a :href="t.link" target="_blank" rel="noopener" class="font-medium hover:underline">
											{{ t.title }}
										</a>
										<span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium tabular" :class="left(t).cls">{{ left(t).text }}</span>
									</div>
									<div class="mt-0.5 text-sm text-gray-600">{{ t.entity }}</div>
									<div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
										<span v-if="isNew(t)" class="rounded bg-blue-50 px-1.5 py-0.5 font-medium text-blue-700">New</span>
										<span>Closes {{ when(t.closing) }}</span>
										<span v-if="t.ref">Ref {{ t.ref }}</span>
										<span v-if="t.method">{{ t.method }}</span>
										<span v-if="t.limited" class="text-amber-700">Limited</span>
										<span v-if="t.value" class="font-medium text-gray-700">{{ money(t.value, t.currency) }}</span>
									</div>
									<div class="mt-2 flex flex-wrap items-center gap-1.5">
										<button v-for="c in t.categories" :key="c" class="max-w-full truncate rounded-full border px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
											:title="c" @click="category = c">{{ c }}</button>
										<span class="flex-1" />
										<a v-if="t.pdf" :href="t.pdf" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900">
											<FeatherIcon name="file" class="h-3.5 w-3.5" /> Notice
										</a>
										<a :href="t.link" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900">
											Portal <FeatherIcon name="external-link" class="h-3.5 w-3.5" />
										</a>
									</div>
								</div>
							</div>
						</li>
					</ul>

					<div v-if="loading && !visible.length" class="p-6 text-center text-gray-500"><LoadingIndicator class="inline h-5 w-5" /></div>
					<div v-else-if="!visible.length" class="p-10 text-center text-gray-500">
						No tenders match. <button class="underline" @click="reset">Clear filters</button>
					</div>
					<div v-else-if="filtered.length > visible.length" class="border-t p-3 text-center">
						<Button :label="`Show ${Math.min(PAGE, filtered.length - visible.length)} more`" @click="shown += PAGE" />
					</div>
				</section>

				<!-- Where the work is: category mix for the current country / window -->
				<aside class="hidden lg:block">
					<section class="sticky top-[4.5rem] rounded-lg border bg-white">
						<header class="border-b px-4 py-3">
							<h3 class="font-semibold">By category</h3>
							<div class="text-xs text-gray-500">{{ view }} · {{ country }}</div>
						</header>
						<ul class="max-h-[70vh] overflow-y-auto py-1">
							<li v-for="c in categoryCounts" :key="c.name">
								<button class="w-full px-4 py-1.5 text-left hover:bg-gray-50" :class="category === c.name ? 'bg-gray-100' : ''"
									@click="category = category === c.name ? '' : c.name">
									<div class="flex items-baseline justify-between gap-2 text-sm">
										<span class="line-clamp-2">{{ c.name }}</span>
										<span class="shrink-0 font-medium tabular">{{ c.count }}</span>
									</div>
									<div class="mt-1 h-1 rounded bg-gray-100">
										<div class="h-1 rounded bg-gray-700" :style="{ width: `${(c.count / categoryCounts[0].count) * 100}%` }" />
									</div>
								</button>
							</li>
							<li v-if="!categoryCounts.length" class="px-4 py-6 text-center text-sm text-gray-500">Nothing here.</li>
						</ul>
					</section>
				</aside>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, h, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { FeatherIcon, LoadingIndicator, toast } from "frappe-ui"
import { api, errorMessages } from "@/utils/api"
import { money, relative } from "@/utils/format"

const COUNTRIES = ["All", "Zimbabwe", "Zambia"]
const WINDOWS = ["Open", "Closing this week", "New", "Closed"]
const PAGE = 50
const DAY = 86400000

const route = useRoute()
const router = useRouter()

// filters live in the query string so a view can be shared or bookmarked
const country = ref(COUNTRIES.includes(route.query.country) ? route.query.country : "All")
const view = ref(WINDOWS.includes(route.query.view) ? route.query.view : "Open")
const category = ref(route.query.category || "")
const search = ref("")
const shown = ref(PAGE)

const open = ref(null)
const closed = ref(null)
const scraped = ref({})
const loading = ref(false)
const now = ref(Date.now())

const ts = (v) => new Date(String(v).replace(" ", "T")).getTime()
const isNew = (t) => now.value - ts(t.created) < DAY

async function load(wantClosed = view.value === "Closed") {
	loading.value = true
	try {
		const r = await api("get_tenders", { closed: wantClosed ? 1 : 0 })
		;(wantClosed ? closed : open).value = r.tenders
		scraped.value = r.last_scraped
		now.value = Date.now()
	} catch (e) {
		toast({ title: "Couldn't load tenders", text: errorMessages(e).join("\n"), icon: "alert-triangle", iconClasses: "text-red-600" })
	} finally {
		loading.value = false
	}
}

function setView(w) {
	view.value = w
	if (w === "Closed" && !closed.value) load(true)
}

// the tiles always count open tenders, so refresh those too when looking at closed ones
const refresh = () => (view.value === "Closed" ? Promise.all([load(false), load(true)]) : load(false))

function reset() {
	country.value = "All"
	category.value = ""
	search.value = ""
	setView("Open")
}

watch([country, view, category], () => {
	shown.value = PAGE
	const q = { country: country.value, view: view.value, category: category.value || undefined }
	router.replace({ query: Object.fromEntries(Object.entries(q).filter(([k, v]) => v && v !== { country: "All", view: "Open" }[k])) })
})
watch(search, () => (shown.value = PAGE))

const inCountry = (rows, c = country.value) => (c === "All" ? rows : rows.filter((t) => t.country === c))

// country + window, before category / search: what the tiles and category panel count
const scoped = computed(() => {
	if (view.value === "Closed") return inCountry(closed.value || [])
	const rows = inCountry(open.value || [])
	if (view.value === "Closing this week") return rows.filter((t) => ts(t.closing) - now.value <= 7 * DAY)
	if (view.value === "New") return rows.filter(isNew)
	return rows
})

const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	return scoped.value.filter(
		(t) =>
			(!category.value || t.categories.includes(category.value)) &&
			(!q || [t.title, t.entity, t.ref].some((v) => (v || "").toLowerCase().includes(q)))
	)
})
const visible = computed(() => filtered.value.slice(0, shown.value))

const categoryCounts = computed(() => {
	const counts = {}
	for (const t of scoped.value) for (const c of t.categories.length ? t.categories : ["Uncategorised"]) counts[c] = (counts[c] || 0) + 1
	return Object.entries(counts).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
})

const tiles = computed(() => {
	const all = open.value || []
	const pick = (c, w) => () => {
		country.value = c
		category.value = ""
		setView(w)
	}
	const tile = (label, rows, c, w, hint, tone = "") => ({
		label, count: rows.length, hint, tone, apply: pick(c, w), active: country.value === c && view.value === w,
	})
	return [
		tile("Open tenders", all, "All", "Open", "Both countries"),
		tile("Zimbabwe", inCountry(all, "Zimbabwe"), "Zimbabwe", "Open", "Open on e-GP"),
		tile("Zambia", inCountry(all, "Zambia"), "Zambia", "Open", "Open on ZPPA"),
		tile("Closing this week", all.filter((t) => ts(t.closing) - now.value <= 7 * DAY), "All", "Closing this week", "Within 7 days", "text-amber-700"),
		tile("New today", all.filter(isNew), "All", "New", "Picked up in the last 24h", "text-blue-700"),
	]
})

const scrapedLine = computed(() => {
	const parts = Object.entries(scraped.value).filter(([, v]) => v).map(([c, v]) => `${c} ${relative(v)}`)
	return parts.length ? `Last picked up: ${parts.join(" · ")}` : "Zimbabwe e-GP and Zambia ZPPA, collected daily"
})

// same thresholds as the email digest: red inside 3 days, amber inside 7
function left(t) {
	const ms = ts(t.closing) - now.value
	if (ms <= 0) return { text: "Closed", cls: "bg-gray-100 text-gray-600" }
	const d = Math.floor(ms / DAY)
	const hrs = Math.floor((ms % DAY) / 3600000)
	const text = d ? `${d}d ${hrs}h left` : hrs ? `${hrs}h left` : `${Math.max(1, Math.floor(ms / 60000))}m left`
	const cls = d < 3 ? "bg-red-50 text-red-700" : d < 7 ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-700"
	return { text, cls }
}

const when = (v) =>
	new Date(ts(v)).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })

const Chip = (props, { slots }) =>
	h("button", {
		class: ["shrink-0 rounded-full border px-3 py-1 text-sm transition-colors",
			props.on ? "border-gray-900 bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-50"],
	}, slots.default())
Chip.props = ["on"]

refresh()
</script>
