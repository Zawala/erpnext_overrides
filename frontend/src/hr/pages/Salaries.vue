<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Salaries" subtitle="Type what each person takes home — the gross is worked out with the real deductions and PAYE">
			<Button class="hidden sm:inline-flex" icon-left="file-text" label="Pay report" @click="$router.push('/pay-report')" />
		</PageHeader>

		<div v-if="!setup" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<!-- What every salary below is priced on -->
			<section class="grid grid-cols-1 gap-4 rounded-lg border bg-white p-4 sm:grid-cols-2 xl:grid-cols-4">
				<label>
					<span class="mb-1.5 flex justify-between text-sm text-gray-600">Salary structure
						<router-link to="/pay-setup" class="text-xs underline">Change structures</router-link></span>
					<select v-model="f.structure" class="form-select w-full">
						<option value="" disabled>Pick a structure</option>
						<option v-for="s in setup.structures" :key="s.name" :value="s.name">{{ s.name }}</option>
					</select>
				</label>
				<label>
					<span class="mb-1.5 block text-sm text-gray-600">From</span>
					<input v-model="f.from_date" type="date" class="form-input w-full" />
				</label>
				<label>
					<span class="mb-1.5 block text-sm text-gray-600">Income tax slab<span v-if="structure?.tax_component" class="text-red-500"> *</span></span>
					<select v-model="f.slab" class="form-select w-full">
						<option value="">{{ structure?.tax_component ? "Pick a slab" : "None" }}</option>
						<option v-for="t in setup.tax_slabs" :key="t.name" :value="t.name">{{ t.name }}</option>
					</select>
				</label>
				<label>
					<span class="mb-1.5 block text-sm text-gray-600">Department</span>
					<LinkField v-model="f.department" doctype="Department" placeholder="Everyone" />
				</label>
			</section>

			<div v-if="blockers.length" class="space-y-1 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
				<p v-for="b in blockers" :key="b.text">{{ b.text }}
					<a v-if="b.href" :href="b.href" target="_blank" class="underline">{{ b.link }} ↗</a></p>
			</div>

			<div v-if="only" class="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-2 text-sm">
				<span>Showing {{ shown[0]?.employee_name || only }} only</span>
				<button class="underline" @click="showEveryone">Show everyone</button>
			</div>

			<!-- One row per person -->
			<section class="rounded-lg border bg-white">
				<div class="hidden border-b bg-gray-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-gray-500 lg:grid" :class="COLS">
					<div>Employee</div><div>Now</div><div>They know</div><div>Their payslip</div>
				</div>
				<div v-if="!rows" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<p v-else-if="!shown.length" class="px-4 py-6 text-center text-sm text-gray-500">Nobody active had joined by {{ date(f.from_date) }}.</p>
				<div v-for="r in shown" :key="r.name" class="grid grid-cols-1 gap-3 border-t px-4 py-3 first:border-t-0 lg:items-start" :class="COLS">
					<div class="min-w-0">
						<router-link :to="`/people/${r.name}`" class="font-medium hover:underline">{{ r.employee_name }}</router-link>
						<div class="truncate text-xs text-gray-500">{{ [r.department, r.designation].filter(Boolean).join(" · ") || "No department" }}</div>
					</div>

					<div class="text-sm">
						<template v-if="r.assignment">
							<div v-if="r.agreed_net_pay">Net <span class="font-medium tabular">{{ m(r.agreed_net_pay) }}</span></div>
							<div class="text-gray-500">Gross <span class="tabular">{{ m(r.base) }}</span> since {{ date(r.assigned_from) }}</div>
							<div v-if="r.salary_structure !== f.structure" class="text-xs text-gray-400">{{ r.salary_structure }}</div>
						</template>
						<div v-else class="text-red-600">No salary — no payslip</div>
						<div v-if="r.drift" class="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
							{{ monthName(r.drift.start_date) }} paid {{ m(r.drift.net_pay) }}, not {{ m(r.agreed_net_pay) }}.
							<button class="underline" @click="regross(r)">Re-gross</button>
						</div>
					</div>

					<div>
						<div class="flex gap-2">
							<div class="flex shrink-0 rounded border p-0.5 text-sm" role="radiogroup" :aria-label="`What ${r.employee_name}'s amount is`">
								<button v-for="mo in ['net', 'gross']" :key="mo" role="radio" :aria-checked="r.mode === mo" :disabled="r.locked"
									class="rounded px-2 py-0.5 capitalize" :class="r.mode === mo ? 'bg-gray-900 text-white' : 'text-gray-600'"
									@click="setMode(r, mo)">{{ mo }}</button>
							</div>
							<input v-model.number="r.amount" type="number" min="0" step="0.01" inputmode="decimal" :disabled="r.locked || blocked"
								class="form-input w-full min-w-0 text-right tabular" :placeholder="r.mode === 'net' ? 'Take-home' : 'Gross'"
								:aria-label="`${r.mode} pay for ${r.employee_name}`" @input="schedule(r)" />
						</div>
						<p v-if="r.locked" class="mt-1 text-xs text-gray-500">A submitted payslip already uses their salary from {{ date(f.from_date) }}. Pick a later date to change it.</p>
					</div>

					<div class="text-sm">
						<div v-if="r.pricing" class="flex items-center gap-2 text-gray-500"><LoadingIndicator class="h-4 w-4" /> Working it out…</div>
						<p v-else-if="r.error" class="text-red-700">{{ r.error }}</p>
						<template v-else-if="r.priced">
							<dl class="grid grid-cols-[1fr_auto] gap-x-4 tabular">
								<template v-for="l in r.priced.lines" :key="l.component">
									<dt :class="l.kind === 'employer' ? 'text-gray-400' : 'text-gray-600'">
										{{ l.kind === "deduction" ? "− " : "" }}{{ l.component }}<span v-if="l.kind === 'employer'"> (employer)</span>
									</dt>
									<dd class="text-right" :class="l.kind === 'employer' ? 'text-gray-400' : ''">{{ m(l.amount) }}</dd>
								</template>
								<dt class="mt-1 border-t pt-1 font-semibold">Net pay</dt>
								<dd class="mt-1 border-t pt-1 text-right font-semibold">{{ m(r.priced.net) }}</dd>
							</dl>
							<p v-if="r.priced.mode === 'net' && Math.abs(r.priced.net - r.priced.amount) >= 0.01" class="mt-1 text-xs text-amber-700">
								{{ m(r.priced.amount) }} can't be hit to the cent; this is the closest.
							</p>
							<p class="mt-1 text-xs" :class="changed(r) ? 'text-blue-700' : 'text-gray-400'">
								{{ changed(r) ? `New gross ${m(r.priced.base)} — not saved yet` : "Same as now" }}
							</p>
						</template>
						<p v-else class="text-gray-400">—</p>
					</div>
				</div>
			</section>

			<div v-if="failed.length" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
				<p class="font-medium">Not saved:</p>
				<p v-for="x in failed" :key="x.employee">{{ nameOf(x.employee) }} — {{ x.error }}</p>
			</div>

			<footer class="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 rounded-lg border bg-white px-4 py-3 shadow-sm">
				<span class="mr-auto hidden text-sm text-gray-500 sm:inline">
					The agreed net is kept with the salary. If a later payslip pays something else, Home and this page flag it.
				</span>
				<Button variant="solid" :label="toSave.length ? `Save ${toSave.length} salar${toSave.length === 1 ? 'y' : 'ies'}` : 'Nothing to save'"
					:disabled="!toSave.length || blocked || anyPricing" :loading="saving" @click="save" />
			</footer>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { LoadingIndicator } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { money, date } from "@/utils/format"
import { boot } from "@/boot"
import { hr, ok, fail, deskUrl } from "../api"
import PageHeader from "../components/PageHeader.vue"

const COLS = "lg:grid-cols-[minmax(11rem,1fr)_minmax(11rem,1fr)_minmax(15rem,1.1fr)_minmax(16rem,1.3fr)] lg:gap-6"
const route = useRoute()
const router = useRouter()

const setup = ref(null)
const rows = ref(null)
const failed = ref([])
const saving = ref(false)
const only = ref(route.query.employee || "")
const now = new Date()
const f = reactive({
	structure: "", slab: "", department: "",
	from_date: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`,
})

const m = (v) => money(v || 0, boot.currency)
const monthName = (d) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { month: "long" })
const nameOf = (id) => rows.value?.find((r) => r.name === id)?.employee_name || id
const structure = computed(() => setup.value?.structures.find((s) => s.name === f.structure))
const shown = computed(() => (rows.value || []).filter((r) => (!only.value || r.name === only.value) && (!f.department || r.department === f.department)))
const anyPricing = computed(() => shown.value.some((r) => r.pricing || r.timer))
const changed = (r) => r.priced && !r.error && (
	Math.abs(r.priced.base - (r.base || 0)) >= 0.005 || r.salary_structure !== f.structure ||
	(r.priced.mode === "net" && Math.abs(r.priced.amount - (r.agreed_net_pay || 0)) >= 0.005)
)
const toSave = computed(() => (rows.value || []).filter((r) => !r.locked && changed(r)))

const blockers = computed(() => {
	const st = setup.value
	const b = []
	if (!st) return b
	if (!st.structures.length) b.push({ text: "No submitted salary structure.", href: "/hrms-admin/pay-setup", link: "Create one in Pay setup" })
	if (!st.payroll_payable_account) b.push({ text: `${boot.company} has no Default Payroll Payable Account, so salaries can't be saved.`, href: deskUrl("Company", boot.company), link: "Set it on the company" })
	if (structure.value && !structure.value.lines) b.push({ text: `${f.structure} has no earnings or deductions.`, href: "/hrms-admin/pay-setup", link: "Add components in Pay setup" })
	if (structure.value?.tax_component && !f.slab)
		b.push(st.tax_slabs.length
			? { text: `${f.structure} deducts ${structure.value.tax_component}: pick the income tax slab.` }
			: { text: `${f.structure} deducts ${structure.value.tax_component} but there is no income tax slab.`, href: "/hrms-admin/pay-setup?tab=tax", link: "Create them in Pay setup" })
	return b
})
// Payable account only blocks saving; pricing works without it
const blocked = computed(() => blockers.value.some((b) => !b.text.includes("Payable")))

function showEveryone() {
	only.value = ""
	router.replace({ query: {} })
}

// Pricing: edits are batched, 400 ms after the last keystroke
const pending = new Set()
let timer = null
function schedule(r) {
	r.timer = true
	pending.add(r)
	clearTimeout(timer)
	timer = setTimeout(priceNow, 400)
}
async function priceNow() {
	const batch = [...pending].filter((r) => {
		r.timer = false
		if (!(Number(r.amount) > 0)) {
			r.priced = null
			r.error = null
			return false
		}
		return true
	})
	pending.clear()
	if (!batch.length || blocked.value) return
	batch.forEach((r) => (r.pricing = true))
	try {
		const out = await hr("price_salaries", {
			salary_structure: f.structure, from_date: f.from_date, income_tax_slab: f.slab || undefined,
			rows: batch.map((r) => ({ employee: r.name, mode: r.mode, amount: r.amount })),
		})
		for (const p of out) {
			const r = batch.find((x) => x.name === p.employee)
			if (Number(r.amount) !== p.amount || r.mode !== (p.mode || r.mode)) continue // edited again meanwhile
			r.error = p.error || null
			r.priced = p.error ? null : p
		}
	} catch (e) {
		batch.forEach((r) => (r.error = e.messages?.[0] || "Could not work it out"))
	} finally {
		batch.forEach((r) => (r.pricing = false))
	}
}

function setMode(r, mode) {
	if (r.mode === mode) return
	r.mode = mode
	r.amount = mode === "net" ? r.agreed_net_pay || (r.priced?.net ?? "") : r.priced?.base ?? r.base ?? ""
	schedule(r)
}
function regross(r) {
	r.mode = "net"
	r.amount = r.agreed_net_pay
	schedule(r)
}
function repriceAll() {
	for (const r of shown.value) if (Number(r.amount) > 0) pending.add(r)
	clearTimeout(timer)
	timer = setTimeout(priceNow, 0)
}

async function loadRows() {
	failed.value = []
	if (!f.from_date) return
	try {
		const list = await hr("get_salaries", { from_date: f.from_date })
		rows.value = list.map((e) => reactive({
			...e, mode: "net", amount: e.agreed_net_pay || "", priced: null, error: null, pricing: false, timer: false,
		}))
		// people who already have an agreed net are priced straight away, so drift and structure changes show
		repriceAll()
		if (route.query.mode === "net" && only.value) {
			const r = rows.value.find((x) => x.name === only.value)
			if (r?.agreed_net_pay) regross(r)
		}
	} catch (e) {
		fail(e, "Could not load salaries")
	}
}

async function save() {
	saving.value = true
	try {
		const out = await hr("save_salaries", {
			salary_structure: f.structure, from_date: f.from_date, income_tax_slab: f.slab || undefined,
			rows: toSave.value.map((r) => ({ employee: r.name, base: r.priced.base, agreed_net: r.priced.mode === "net" ? r.priced.amount : r.priced.net })),
		})
		const saved = out.created + out.replaced
		ok(`Saved ${saved} salar${saved === 1 ? "y" : "ies"}`, out.failed.length ? `${out.failed.length} not saved — see below` : "They'll be paid this from the next run")
		const notSaved = out.failed
		await loadRows()
		failed.value = notSaved
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

watch(() => f.from_date, loadRows)
watch(() => [f.structure, f.slab], () => rows.value && repriceAll())

hr("get_structure_setup").then((s) => {
	setup.value = s
	f.structure = s.structures.find((x) => x.lines && x.tax_component)?.name || s.structures[0]?.name || ""
	f.slab = s.tax_slabs[0]?.name || ""
	loadRows()
}).catch((e) => fail(e, "Could not load salary structures"))
</script>
