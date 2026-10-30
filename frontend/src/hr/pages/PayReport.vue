<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Pay report" subtitle="What each person earned, had deducted and was paid — from their salary slips">
			<Button icon-left="download" label="CSV" :disabled="!data?.rows.length" @click="exportCsv" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1800px] p-4 lg:p-6 space-y-4">
			<!-- Filters -->
			<div class="flex flex-wrap items-end gap-3">
				<Chips v-model="preset" :options="presets" />
				<label><span class="mb-1 block text-xs text-gray-500">From</span>
					<input v-model="f.from_date" type="date" class="form-input" @change="preset = ''" /></label>
				<label><span class="mb-1 block text-xs text-gray-500">To</span>
					<input v-model="f.to_date" type="date" class="form-input" @change="preset = ''" /></label>
				<label class="w-48"><span class="mb-1 block text-xs text-gray-500">Department</span>
					<LinkField v-model="f.department" doctype="Department" placeholder="Everyone" /></label>
				<label class="w-56"><span class="mb-1 block text-xs text-gray-500">Employee</span>
					<LinkField v-model="f.employee" doctype="Employee" placeholder="Everyone" /></label>
				<label class="flex items-center gap-2 pb-1.5 text-sm text-gray-700">
					<input v-model="f.include_drafts" type="checkbox" class="form-checkbox" /> Include draft slips</label>
			</div>

			<div v-if="loading && !data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<Empty v-else-if="data && !data.rows.length" icon="file-text">
				No {{ f.include_drafts ? "" : "submitted " }}salary slips between {{ date(f.from_date) }} and {{ date(f.to_date) }}.
				<template v-if="!f.include_drafts"> Tick “Include draft slips” to see a run that hasn't been submitted.</template>
			</Empty>

			<template v-else-if="data">
				<!-- Totals -->
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-6">
					<Tile label="People" :value="data.rows.length" :hint="`${data.slips} slip${data.slips === 1 ? '' : 's'}`" />
					<Tile label="Gross pay" :value="m(data.totals.gross_pay)" />
					<Tile label="Deductions" :value="m(data.totals.total_deduction)" />
					<Tile label="Net pay" :value="m(data.totals.net_pay)" strong />
					<Tile v-for="c in data.groups.deductions" :key="c" :label="c" :value="m(data.totals.amounts[c])" muted />
					<Tile v-for="c in data.groups.other" :key="c" :label="c" :value="m(data.totals.amounts[c])" hint="Not in net pay" muted />
				</div>
				<p v-if="f.include_drafts && hasDrafts" class="text-sm text-amber-700">Includes draft slips — these figures can still change.</p>

				<!-- Per person -->
				<div class="overflow-x-auto rounded-lg border bg-white">
					<table class="w-full text-sm tabular">
						<thead class="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
							<tr>
								<th rowspan="2" class="sticky left-0 z-10 min-w-[12rem] border-r bg-gray-50 px-4 py-2 text-left font-medium">Employee</th>
								<th v-if="data.groups.earnings.length" :colspan="data.groups.earnings.length + 1" class="border-l px-2 pt-2 text-center font-medium">Earnings</th>
								<th v-if="data.groups.deductions.length" :colspan="data.groups.deductions.length + 1" class="border-l px-2 pt-2 text-center font-medium">Deductions</th>
								<th rowspan="2" class="border-l px-3 py-2 text-right font-semibold text-gray-700">Net pay</th>
								<th v-if="data.groups.other.length" :colspan="data.groups.other.length" class="border-l px-2 pt-2 text-center font-medium">Not in pay</th>
							</tr>
							<tr>
								<th v-for="c in data.groups.earnings" :key="c" class="min-w-[6.5rem] max-w-[9rem] border-l px-3 py-2 text-right align-bottom font-medium normal-case leading-tight">{{ c }}</th>
								<th v-if="data.groups.earnings.length" class="border-l px-3 py-2 text-right font-semibold text-gray-700">Gross</th>
								<th v-for="c in data.groups.deductions" :key="c" class="min-w-[6.5rem] max-w-[9rem] border-l px-3 py-2 text-right align-bottom font-medium normal-case leading-tight">{{ c }}</th>
								<th v-if="data.groups.deductions.length" class="border-l px-3 py-2 text-right font-semibold text-gray-700">Total</th>
								<th v-for="c in data.groups.other" :key="c" class="min-w-[6.5rem] max-w-[9rem] border-l px-3 py-2 text-right align-bottom font-medium normal-case leading-tight">{{ c }}</th>
							</tr>
						</thead>
						<tbody>
							<template v-for="r in data.rows" :key="r.employee">
								<tr class="cursor-pointer border-t hover:bg-gray-50" @click="toggle(r.employee)">
									<td class="sticky left-0 z-10 border-r bg-white px-4 py-2">
										<div class="flex items-center gap-2">
											<FeatherIcon :name="open.has(r.employee) ? 'chevron-down' : 'chevron-right'" class="h-4 w-4 shrink-0 text-gray-400" />
											<div class="min-w-0">
												<router-link :to="`/people/${r.employee}`" class="font-medium hover:underline" @click.stop>{{ r.employee_name }}</router-link>
												<div class="truncate text-xs text-gray-500">{{ r.department || "No department" }} · {{ r.slips.length }} slip{{ r.slips.length === 1 ? "" : "s" }}</div>
											</div>
										</div>
									</td>
									<Cells :row="r" :groups="data.groups" :m="m" />
								</tr>
								<tr v-for="s in open.has(r.employee) ? r.slips : []" :key="s.name" class="border-t bg-gray-50/60 text-gray-600">
									<td class="sticky left-0 z-10 border-r bg-gray-50 py-1.5 pl-10 pr-4">
										<router-link :to="`/records/salary-slips/${s.name}`" class="hover:underline">{{ month(s.start_date, s.end_date) }}</router-link>
										<span v-if="!s.docstatus" class="ml-1.5 rounded bg-amber-100 px-1 text-xs text-amber-800">Draft</span>
										<div v-if="s.payment_days < s.total_working_days" class="text-xs text-amber-700">Paid {{ s.payment_days }} of {{ s.total_working_days }} days</div>
									</td>
									<Cells :row="s" :groups="data.groups" :m="m" />
								</tr>
							</template>
						</tbody>
						<tfoot class="border-t-2 bg-gray-50 font-semibold">
							<tr>
								<td class="sticky left-0 z-10 border-r bg-gray-50 px-4 py-2">Total</td>
								<Cells :row="data.totals" :groups="data.groups" :m="m" />
							</tr>
						</tfoot>
					</table>
				</div>
				<p class="text-xs text-gray-500">
					Click a person for their slips month by month. “Not in pay” is components that don't change net pay — employer contributions and statistical lines.
				</p>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, h, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { LoadingIndicator } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { money, date } from "@/utils/format"
import { boot } from "@/boot"
import { hr, fail } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import Empty from "../components/Empty.vue"

const route = useRoute()
const router = useRouter()
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const now = new Date()
const RANGES = {
	month: [new Date(now.getFullYear(), now.getMonth(), 1), new Date(now.getFullYear(), now.getMonth() + 1, 0)],
	last_month: [new Date(now.getFullYear(), now.getMonth() - 1, 1), new Date(now.getFullYear(), now.getMonth(), 0)],
	year: [new Date(now.getFullYear(), 0, 1), new Date(now.getFullYear(), 11, 31)],
	last_year: [new Date(now.getFullYear() - 1, 0, 1), new Date(now.getFullYear() - 1, 11, 31)],
}
const presets = [
	{ value: "month", label: "This month" }, { value: "last_month", label: "Last month" },
	{ value: "year", label: `${now.getFullYear()} to date` }, { value: "last_year", label: String(now.getFullYear() - 1) },
]

const q = route.query
const preset = ref(q.from_date ? "" : q.preset || "year")
const f = reactive({
	from_date: q.from_date || iso(RANGES[preset.value || "year"][0]),
	to_date: q.to_date || iso(RANGES[preset.value || "year"][1]),
	department: q.department || "", employee: q.employee || "", include_drafts: q.drafts === "1",
})
watch(preset, (p) => p && Object.assign(f, { from_date: iso(RANGES[p][0]), to_date: iso(RANGES[p][1]) }))

const data = ref(null)
const loading = ref(false)
const open = ref(new Set())
const currency = computed(() => data.value?.currency || boot.currency)
const m = (v) => money(v || 0, currency.value)
const hasDrafts = computed(() => data.value?.rows.some((r) => r.slips.some((s) => !s.docstatus)))
const month = (start, end) => {
	const s = new Date(start + "T00:00:00")
	const e = new Date(end + "T00:00:00")
	return s.getDate() === 1 && e.getMonth() === s.getMonth() && new Date(e.getFullYear(), e.getMonth() + 1, 0).getDate() === e.getDate()
		? s.toLocaleDateString(undefined, { month: "long", year: "numeric" })
		: `${date(start)} – ${date(end)}`
}

function toggle(id) {
	const s = new Set(open.value)
	s.has(id) ? s.delete(id) : s.add(id)
	open.value = s
}

async function load() {
	loading.value = true
	router.replace({ query: {
		...(preset.value ? { preset: preset.value } : { from_date: f.from_date, to_date: f.to_date }),
		...(f.department && { department: f.department }), ...(f.employee && { employee: f.employee }),
		...(f.include_drafts && { drafts: "1" }),
	} })
	try {
		data.value = await hr("get_pay_report", {
			from_date: f.from_date, to_date: f.to_date, department: f.department || undefined,
			employee: f.employee || undefined, include_drafts: f.include_drafts ? 1 : 0,
		})
		open.value = new Set(data.value.rows.length === 1 ? [data.value.rows[0].employee] : [])
	} catch (e) {
		fail(e, "Could not load the pay report")
	} finally {
		loading.value = false
	}
}
watch(f, load, { deep: true })
load()

function exportCsv() {
	const g = data.value.groups
	const head = ["Employee ID", "Employee", "Department", "Period", ...g.earnings, "Gross pay", ...g.deductions, "Total deductions", "Net pay", ...g.other]
	const line = (r, who, period) => [
		...who, period, ...g.earnings.map((c) => r.amounts[c] || 0), r.gross_pay,
		...g.deductions.map((c) => r.amounts[c] || 0), r.total_deduction, r.net_pay, ...g.other.map((c) => r.amounts[c] || 0),
	]
	const lines = [head]
	for (const r of data.value.rows) {
		const who = [r.employee, r.employee_name, r.department || ""]
		lines.push(line(r, who, `${f.from_date} to ${f.to_date}`))
		for (const s of r.slips) lines.push(line(s, who, `${s.start_date} to ${s.end_date}${s.docstatus ? "" : " (draft)"}`))
	}
	lines.push(line(data.value.totals, ["", "Total", ""], `${f.from_date} to ${f.to_date}`))
	const csv = lines.map((l) => l.map((v) => (typeof v === "number" ? v.toFixed(2) : `"${String(v).replace(/"/g, '""')}"`)).join(",")).join("\n")
	const a = document.createElement("a")
	a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }))
	a.download = `pay-report-${f.from_date}-to-${f.to_date}.csv`
	a.click()
	URL.revokeObjectURL(a.href)
}

// One row of amounts, in the column order of the header
const Cells = (p) => {
	const cell = (v, cls = "") => h("td", { class: `whitespace-nowrap border-l px-3 py-2 text-right ${cls}` }, v ? p.m(v) : "—")
	const g = p.groups
	return [
		...g.earnings.map((c) => cell(p.row.amounts[c])),
		g.earnings.length ? cell(p.row.gross_pay, "font-medium") : null,
		...g.deductions.map((c) => cell(p.row.amounts[c])),
		g.deductions.length ? cell(p.row.total_deduction, "font-medium") : null,
		cell(p.row.net_pay, "font-semibold text-gray-900"),
		...g.other.map((c) => cell(p.row.amounts[c], "text-gray-500")),
	].filter(Boolean)
}
Cells.props = ["row", "groups", "m"]

const Tile = (p) =>
	h("div", { class: ["rounded-lg border bg-white px-4 py-3", p.strong ? "border-gray-900" : ""] }, [
		h("div", { class: "truncate text-xs text-gray-500", title: p.label }, p.label),
		h("div", { class: ["mt-0.5 truncate font-semibold tabular", p.muted ? "text-base text-gray-700" : "text-xl"] }, String(p.value)),
		p.hint ? h("div", { class: "text-xs text-gray-400" }, p.hint) : null,
	])
Tile.props = ["label", "value", "hint", "strong", "muted"]
</script>
