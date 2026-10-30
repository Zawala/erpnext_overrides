<template>
	<div class="flex h-full min-h-0">
		<!-- List pane: full width when nothing is open, a column beside the document otherwise -->
		<section
			class="flex min-h-0 flex-col border-r bg-white"
			:class="docOpen ? 'hidden min-[1600px]:flex w-[380px] shrink-0' : 'flex-1'"
		>
			<header class="flex items-center gap-3 border-b px-4 lg:px-6 h-14 shrink-0">
				<FeatherIcon :name="cfg.icon" class="h-5 w-5 text-gray-500" />
				<h1 class="flex-1 truncate text-lg font-semibold">{{ cfg.label }}</h1>
				<Button v-if="can(cfg.doctype, 'create')" variant="solid" icon-left="plus" :label="docOpen ? 'New' : `New ${cfg.doctype}`"
					@click="$router.push(`/${cfg.slug}/new`)" />
			</header>

			<div class="space-y-3 border-b px-4 lg:px-6 py-3">
				<div class="relative">
					<FeatherIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
					<input v-model="search" type="search" class="form-input w-full pl-8" :placeholder="`Search ${cfg.label.toLowerCase()}`" />
				</div>
				<div class="flex gap-1.5 overflow-x-auto hide-scrollbar">
					<button
						v-for="f in cfg.filters"
						:key="f.label"
						class="shrink-0 rounded-full border px-3 py-1 text-sm transition-colors"
						:class="f.label === active ? 'border-gray-900 bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-50'"
						@click="setFilter(f.label)"
					>
						{{ f.label }}
					</button>
				</div>
			</div>

			<div class="flex-1 overflow-y-auto">
				<!-- Wide table when the list has the page to itself -->
				<table v-if="!docOpen" class="hidden md:table w-full text-base tabular">
					<thead class="sticky top-0 z-10 bg-gray-50">
						<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
							<th class="px-6 py-2 font-medium">{{ cfg.doctype }}</th>
							<th class="px-3 py-2 font-medium">Status</th>
							<th v-for="c in cfg.columns" :key="c.key" class="px-3 py-2 font-medium"
								:class="c.align === 'right' ? 'text-right' : ''">{{ c.label }}</th>
							<th class="px-6 py-2 font-medium text-right">Updated</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in rows" :key="row.name" class="cursor-pointer border-t hover:bg-gray-50" @click="open(row)">
							<td class="px-6 py-2.5">
								<div class="font-medium">{{ cfg.title(row) }}</div>
								<div class="text-sm text-gray-500">{{ row.name }}</div>
							</td>
							<td class="px-3 py-2.5"><StatusBadge :status="status(row)" /></td>
							<td v-for="c in cfg.columns" :key="c.key" class="px-3 py-2.5 text-gray-700"
								:class="c.align === 'right' ? 'text-right font-medium' : ''">{{ fmt(row, c) }}</td>
							<td class="px-6 py-2.5 text-right text-sm text-gray-500">{{ relative(row.modified) }}</td>
						</tr>
					</tbody>
				</table>

				<!-- Cards: mobile, and the narrow column beside an open document -->
				<ul :class="docOpen ? '' : 'md:hidden'" class="divide-y">
					<li v-for="row in rows" :key="row.name">
						<router-link :to="docRoute(cfg.doctype, row.name)"
							class="block px-4 lg:px-5 py-3 hover:bg-gray-50"
							:class="row.name === route.params.name ? 'bg-gray-100' : ''">
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0">
									<div class="truncate font-medium">{{ cfg.title(row) }}</div>
									<div class="truncate text-sm text-gray-500">{{ cfg.subtitle(row) }}</div>
								</div>
								<div class="shrink-0 text-right">
									<div v-if="cfg.amount" class="font-medium tabular">{{ money(cfg.amount(row), row.currency) }}</div>
									<StatusBadge :status="status(row)" size="sm" />
								</div>
							</div>
						</router-link>
					</li>
				</ul>

				<div v-if="loading" class="p-6 text-center text-gray-500"><LoadingIndicator class="inline h-5 w-5" /></div>
				<div v-else-if="!rows.length" class="p-10 text-center text-gray-500">
					Nothing here{{ search ? ` matching “${search}”` : "" }}.
				</div>
				<div v-else-if="hasMore" class="p-4 text-center">
					<Button label="Load more" @click="fetch(true)" />
				</div>
			</div>
		</section>

		<!-- Document pane -->
		<section v-if="docOpen" class="flex-1 min-w-0 min-h-0">
			<router-view :key="route.params.name || 'new'" />
		</section>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { FeatherIcon, LoadingIndicator, call, debounce } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"
import { bySlug, docRoute, can } from "@/doctypes"
import { money, date, relative } from "@/utils/format"
import { listVersions } from "@/data/lists"

const props = defineProps({ slug: String })
const route = useRoute()
const router = useRouter()
const PAGE = 30

const cfg = computed(() => bySlug[props.slug])
const docOpen = computed(() => route.name === "Doc" || route.name === "New")
const active = ref(route.query.f || cfg.value.filters[0].label)
const search = ref("")
const rows = ref([])
const loading = ref(false)
const hasMore = ref(false)

const status = (row) => (cfg.value.submittable && row.docstatus === 0 ? "Draft" : row.status)
const fmt = (row, c) =>
	c.format === "money" ? money(row[c.key], row.currency) : c.format === "date" ? date(row[c.key]) : row[c.key] || "—"

function setFilter(label) {
	active.value = label
	router.replace({ query: { ...route.query, f: label } })
}

async function fetch(more = false) {
	loading.value = true
	const filter = cfg.value.filters.find((f) => f.label === active.value) || cfg.value.filters[0]
	const q = search.value.trim()
	try {
		const page = await call("frappe.client.get_list", {
			doctype: cfg.value.doctype,
			fields: cfg.value.listFields,
			filters: filter.filters,
			or_filters: q ? [["name", "like", `%${q}%`], ...cfg.value.search.map((f) => [f, "like", `%${q}%`])] : undefined,
			order_by: "modified desc",
			limit_start: more ? rows.value.length : 0,
			limit_page_length: PAGE,
		})
		rows.value = more ? [...rows.value, ...page] : page
		hasMore.value = page.length === PAGE
	} finally {
		loading.value = false
	}
}

function open(row) {
	router.push(docRoute(cfg.value.doctype, row.name))
}

watch(() => props.slug, () => {
	active.value = route.query.f || cfg.value.filters[0].label
	search.value = ""
	fetch()
})
watch(active, () => fetch())
watch(search, debounce(() => fetch(), 300))
watch(() => listVersions[cfg.value.doctype], () => fetch())
fetch()
</script>
