<template>
	<div class="flex h-full min-h-0 flex-col">
		<PageHeader :title="cfg.label">
			<Button :link="deskUrl(cfg.doctype)" icon-left="external-link" label="Desk" variant="ghost" />
		</PageHeader>

		<div class="space-y-3 border-b bg-white px-4 lg:px-6 py-3">
			<div class="relative max-w-md">
				<FeatherIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
				<input v-model="search" type="search" class="form-input w-full pl-8" :placeholder="`Search ${cfg.label.toLowerCase()}`" />
			</div>
			<Chips v-model="active" :options="cfg.filters.map((f) => f.label)" />
		</div>

		<div class="flex-1 overflow-y-auto bg-white">
			<table class="hidden md:table w-full text-sm tabular">
				<thead class="sticky top-0 z-10 bg-gray-50">
					<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
						<th class="px-6 py-2 font-medium">{{ cfg.doctype }}</th>
						<th class="px-3 py-2 font-medium">Status</th>
						<th v-for="c in cfg.columns" :key="c.key" class="px-3 py-2 font-medium" :class="right(c) ? 'text-right' : ''">{{ c.label }}</th>
						<th class="px-6 py-2 text-right font-medium">Updated</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="r in rows" :key="r.name" class="cursor-pointer border-t hover:bg-gray-50" @click="open(r)">
						<td class="px-6 py-2.5"><div class="font-medium">{{ cfg.title(r) }}</div><div class="text-xs text-gray-500">{{ r.name }}</div></td>
						<td class="px-3 py-2.5"><StatusBadge :status="cfg.status(r)" size="sm" /></td>
						<td v-for="c in cfg.columns" :key="c.key" class="px-3 py-2.5 text-gray-700" :class="right(c) ? 'text-right' : ''">{{ fmt(r, c) }}</td>
						<td class="px-6 py-2.5 text-right text-gray-500">{{ relative(r.modified) }}</td>
					</tr>
				</tbody>
			</table>
			<ul class="md:hidden divide-y">
				<li v-for="r in rows" :key="r.name">
					<router-link :to="link(r)" class="flex items-start justify-between gap-3 px-4 py-3">
						<div class="min-w-0"><div class="truncate font-medium">{{ cfg.title(r) }}</div><div class="truncate text-sm text-gray-500">{{ cfg.subtitle(r) }}</div></div>
						<StatusBadge :status="cfg.status(r)" size="sm" />
					</router-link>
				</li>
			</ul>
			<div v-if="loading" class="p-6 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<Empty v-else-if="!rows.length">Nothing here{{ search ? ` matching “${search}”` : "" }}.</Empty>
			<div v-else-if="hasMore" class="p-4 text-center"><Button label="Load more" @click="fetch(true)" /></div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { LoadingIndicator, call, debounce } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"
import { money, date, relative } from "@/utils/format"
import { deskUrl, fail } from "../api"
import { records } from "../records"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import Empty from "../components/Empty.vue"

const props = defineProps({ slug: String })
const route = useRoute()
const router = useRouter()
const PAGE = 50

const cfg = computed(() => records[props.slug] || records["leave-applications"])
const active = ref(route.query.f || cfg.value.filters[0].label)
const search = ref("")
const rows = ref([])
const loading = ref(false)
const hasMore = ref(false)

const right = (c) => c.format === "money" || c.format === "days"
const fmt = (r, c) => {
	const v = r[c.key]
	if (c.format === "money") return money(v, r.currency)
	if (c.format === "date") return date(v)
	if (c.format === "days") return Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })
	return v || "—"
}
const link = (r) => `/records/${props.slug}/${encodeURIComponent(r.name)}`
const open = (r) => router.push(link(r))

async function fetch(more = false) {
	loading.value = true
	const f = cfg.value.filters.find((x) => x.label === active.value) || cfg.value.filters[0]
	const q = search.value.trim()
	try {
		const page = await call("frappe.client.get_list", {
			doctype: cfg.value.doctype,
			fields: cfg.value.fields,
			filters: f.filters,
			or_filters: q ? [["name", "like", `%${q}%`], ...cfg.value.search.map((s) => [s, "like", `%${q}%`])] : undefined,
			order_by: "modified desc",
			limit_start: more ? rows.value.length : 0,
			limit_page_length: PAGE,
		})
		rows.value = more ? [...rows.value, ...page] : page
		hasMore.value = page.length === PAGE
	} catch (e) {
		fail(e, "Could not load the list")
	} finally {
		loading.value = false
	}
}

watch(() => props.slug, () => {
	active.value = route.query.f || cfg.value.filters[0].label
	search.value = ""
	fetch()
})
watch(active, (f) => {
	router.replace({ query: { ...route.query, f } })
	fetch()
})
watch(search, debounce(() => fetch(), 300))
fetch()
</script>
