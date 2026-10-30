<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Exchange rates" subtitle="USD↔ZWG from the Reserve Bank (RBZ) each weekday; every ZWG posting uses that day's rate">
			<Button icon-left="download-cloud" label="Fetch from RBZ" :loading="syncing" @click="sync" />
		</PageHeader>

		<div v-if="!rates" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-[1400px] p-4 lg:p-6 space-y-4">
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)] items-start">
				<section class="rounded-lg border bg-white p-4">
					<div class="text-xs text-gray-500">Latest RBZ rate</div>
					<div v-if="rates.latest" class="text-3xl font-semibold tabular">{{ Number(rates.latest.exchange_rate).toFixed(4) }}</div>
					<div v-if="rates.latest" class="text-sm text-gray-500">ZWG per USD · {{ date(rates.latest.date) }}</div>
					<div v-else class="text-sm text-red-700">No rate loaded yet.</div>
					<div v-if="rates.missing.length" class="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900">
						{{ rates.missing.length }} weekday{{ rates.missing.length === 1 ? "" : "s" }} in the last month have no rate, so ZWG lines on those days use the
						last rate before them. <b>Fetch from RBZ</b> fills them in.
					</div>
				</section>

				<section class="rounded-lg border bg-white p-4">
					<h3 class="mb-2 font-semibold">Last 60 days</h3>
					<p v-if="rates.series.length < 2" class="text-sm text-gray-500">Not enough rates in this window to draw — fetch from RBZ.</p>
					<svg v-else viewBox="0 0 800 200" class="h-52 w-full" role="img" aria-label="USD to ZWG over 60 days">
						<polyline :points="points" fill="none" stroke="#111827" stroke-width="2" />
						<text x="4" y="14" class="fill-gray-400 text-[11px]">{{ hi.toFixed(2) }}</text>
						<text x="4" y="196" class="fill-gray-400 text-[11px]">{{ lo.toFixed(2) }}</text>
						<text x="796" y="196" text-anchor="end" class="fill-gray-400 text-[11px]">{{ date(rates.series.at(-1).date) }}</text>
					</svg>
				</section>
			</div>

			<section class="rounded-lg border bg-white">
				<h3 class="border-b px-4 py-3 font-semibold">All currency pairs</h3>
				<table class="w-full text-sm tabular">
					<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
						<tr><th class="px-4 py-2">Pair</th><th class="px-2 py-2 text-right">Rate</th><th class="px-2 py-2">As of</th><th class="px-4 py-2">Source</th></tr>
					</thead>
					<tbody>
						<tr v-for="p in rates.pairs" :key="p.from_currency + p.to_currency" class="border-t">
							<td class="px-4 py-2">{{ p.from_currency }} → {{ p.to_currency }}</td>
							<td class="px-2 py-2 text-right">{{ Number(p.rate).toFixed(6) }}</td>
							<td class="px-2 py-2">{{ date(p.last_date) }}</td>
							<td class="px-4 py-2">{{ p.source === "RBZ" ? "RBZ (daily sheet)" : `${rates.provider || "ERPNext"} (on demand)` }}</td>
						</tr>
					</tbody>
				</table>
				<p class="border-t px-4 py-3 text-sm text-gray-500">
					Other currencies (ZAR, EUR, GBP…) are fetched when a document needs them, from {{ rates.provider || "ERPNext's provider" }}.
					XE.com rates need an XE API account; once finance has one, it is set in desk → Currency Exchange Settings.
				</p>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { LoadingIndicator } from "frappe-ui"
import { date } from "@/utils/format"
import { acc, ok, fail } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"

const rates = ref(null)
const syncing = ref(false)
const values = computed(() => (rates.value?.series || []).map((r) => Number(r.exchange_rate)))
const lo = computed(() => Math.min(...values.value))
const hi = computed(() => Math.max(...values.value))
const points = computed(() => {
	const n = values.value.length
	const span = hi.value - lo.value || 1
	return values.value.map((v, i) => `${(i / (n - 1)) * 790 + 5},${185 - ((v - lo.value) / span) * 165}`).join(" ")
})

async function load() {
	try {
		rates.value = await acc("get_rates")
	} catch (e) {
		fail(e, "Could not load the rates")
	}
}

async function sync() {
	syncing.value = true
	try {
		rates.value = await acc("sync_rbz", { days: 45 })
		ok("Rates fetched from RBZ", rates.value.missing.length ? `${rates.value.missing.length} days still missing (holidays, or not published yet)` : "No gaps")
	} catch (e) {
		fail(e, "RBZ didn't answer")
	} finally {
		syncing.value = false
	}
}

load()
</script>
