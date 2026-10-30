<template>
	<div class="flex h-full min-h-0 flex-col">
		<PageHeader :title="run ? `Payroll ${date(run.doc.start_date)} – ${date(run.doc.end_date)}` : 'Payroll run'" :subtitle="name" back="/payroll">
			<template #badge><StatusBadge v-if="run" :status="badge" /></template>
			<Button :link="deskUrl('Payroll Entry', name)" icon-left="external-link" label="Desk" variant="ghost" />
		</PageHeader>

		<div v-if="!run" class="flex flex-1 items-center justify-center"><LoadingIndicator class="h-5 w-5 text-gray-500" /></div>
		<div v-else class="flex-1 overflow-y-auto">
			<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
				<!-- Stepper -->
				<ol class="grid grid-cols-2 gap-2 sm:grid-cols-5">
					<li v-for="(s, i) in steps" :key="s.key" class="rounded-lg border bg-white p-3"
						:class="i === active ? 'border-gray-900 ring-1 ring-gray-900' : ''">
						<div class="flex items-center justify-between text-sm">
							<span class="font-semibold text-gray-400">{{ i + 1 }}</span>
							<FeatherIcon v-if="i < active || done" name="check-circle" class="h-4 w-4 text-green-600" />
						</div>
						<div class="mt-1 font-medium">{{ s.label }}</div>
						<div class="text-xs text-gray-500">{{ s.hint }}</div>
					</li>
				</ol>

				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 space-y-1">
					<p v-for="m in errors" :key="m">{{ m }}</p>
				</div>
				<div v-if="run.state.state === 'queued'" class="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
					<LoadingIndicator class="h-4 w-4" /> Working in the background — this page refreshes by itself.
				</div>
				<div v-if="run.state.state === 'failed'" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
					The last step failed: {{ strip(run.state.error) || "see the Error Log in desk" }}
				</div>

				<!-- What to do now -->
				<section class="rounded-lg border bg-white p-4">
					<div class="flex flex-wrap items-center gap-4">
						<div class="min-w-0 flex-1">
							<h3 class="font-semibold">{{ next.title }}</h3>
							<p class="text-sm text-gray-600">{{ next.text }}</p>
						</div>
						<div v-if="next.step === 'bank_entry'" class="w-full sm:w-72">
							<LinkField v-model="paymentAccount" doctype="Account" placeholder="Bank account to pay from"
								:filters="{ account_type: ['in', ['Bank', 'Cash']], is_group: 0, company: run.doc.company }" />
						</div>
						<Button v-if="next.step" variant="solid" size="lg" :label="next.button" :loading="busy"
							:disabled="run.state.state === 'queued'" @click="next.step === 'submit_slips' ? (confirmOpen = true) : step(next.step)" />
						<template v-if="run.state.bank_entries">
							<Button v-for="je in run.state.bank_entries" :key="je" :link="deskUrl('Journal Entry', je)" icon-left="external-link" :label="je" />
						</template>
					</div>
				</section>

				<!-- Totals -->
				<section v-if="run.slips.length" class="grid grid-cols-2 gap-3 md:grid-cols-4">
					<div class="rounded-lg border bg-white p-4"><div class="text-sm text-gray-600">Slips</div><div class="text-2xl font-semibold tabular">{{ run.slips.length }}</div></div>
					<div class="rounded-lg border bg-white p-4"><div class="text-sm text-gray-600">Gross</div><div class="text-2xl font-semibold tabular">{{ money(run.totals.gross, run.doc.currency) }}</div></div>
					<div class="rounded-lg border bg-white p-4"><div class="text-sm text-gray-600">Deductions</div><div class="text-2xl font-semibold tabular">{{ money(run.totals.deductions, run.doc.currency) }}</div></div>
					<div class="rounded-lg border bg-white p-4"><div class="text-sm text-gray-600">Net pay</div><div class="text-2xl font-semibold tabular">{{ money(run.totals.net, run.doc.currency) }}</div></div>
				</section>

				<!-- Slips -->
				<section v-if="run.slips.length" class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<div>
							<h3 class="font-semibold">Salary slips</h3>
							<p class="text-sm text-gray-500">Check before you submit — a wrong base or a missing leave record is fixed at source, never on the slip.</p>
						</div>
						<span v-if="flagged" class="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm font-medium text-amber-800">{{ flagged }} to check</span>
					</header>
					<div class="hidden md:block overflow-x-auto">
						<table class="w-full text-sm tabular">
							<thead class="bg-gray-50">
								<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
									<th class="px-4 py-2 font-medium">Employee</th>
									<th class="px-2 py-2 text-right font-medium">Days paid</th>
									<th class="px-2 py-2 text-right font-medium">Gross</th>
									<th class="px-2 py-2 text-right font-medium">Deductions</th>
									<th class="px-2 py-2 text-right font-medium">Net</th>
									<th class="px-4 py-2 font-medium">Check</th>
									<th class="w-10"></th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="s in run.slips" :key="s.name" class="border-t">
									<td class="px-4 py-2">
										<div class="font-medium">{{ s.employee_name }}</div>
										<div class="text-xs text-gray-500">{{ s.name }} · {{ s.docstatus ? "Submitted" : "Draft" }}</div>
									</td>
									<td class="px-2 py-2 text-right">{{ n(s.payment_days) }} / {{ n(s.total_working_days) }}</td>
									<td class="px-2 py-2 text-right">{{ money(s.gross_pay, s.currency) }}</td>
									<td class="px-2 py-2 text-right">{{ money(s.total_deduction, s.currency) }}</td>
									<td class="px-2 py-2 text-right font-medium">{{ money(s.net_pay, s.currency) }}</td>
									<td class="px-4 py-2">
										<span v-for="f in s.flags" :key="f" class="mr-1 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800">{{ f }}</span>
									</td>
									<td class="pr-3"><Button icon="printer" variant="ghost" label="Payslip" @click="printSlip = s.name" /></td>
								</tr>
							</tbody>
						</table>
					</div>
					<ul class="md:hidden divide-y">
						<li v-for="s in run.slips" :key="s.name" class="px-4 py-3" @click="printSlip = s.name">
							<div class="flex justify-between gap-3">
								<div class="min-w-0"><div class="truncate font-medium">{{ s.employee_name }}</div>
									<div class="text-sm text-gray-500">{{ n(s.payment_days) }} / {{ n(s.total_working_days) }} days</div></div>
								<div class="font-medium tabular">{{ money(s.net_pay, s.currency) }}</div>
							</div>
							<div v-if="s.flags.length" class="mt-1 text-xs text-amber-700">{{ s.flags.join(" · ") }}</div>
						</li>
					</ul>
				</section>

				<!-- Employees picked up, before slips exist -->
				<section v-else-if="run.doc.employees.length" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">{{ run.doc.employees.length }} employees in this run</h3>
					<ul class="grid grid-cols-1 divide-y sm:grid-cols-2 sm:divide-y-0 xl:grid-cols-3">
						<li v-for="e in run.doc.employees" :key="e.employee" class="px-4 py-2 text-sm">
							<div class="font-medium">{{ e.employee_name }}</div><div class="text-gray-500">{{ e.department || e.employee }}</div>
						</li>
					</ul>
				</section>
			</div>
		</div>

		<Dialog v-model="confirmOpen" :options="{ title: 'Submit the salary slips?', size: 'md' }">
			<template #body-content>
				<p class="text-sm text-gray-700">
					This submits {{ run?.slips.filter((s) => !s.docstatus).length }} slips and posts the accrual journal entry to the accounts.
					Nobody can edit a submitted slip — a wrong one is cancelled and amended.
				</p>
				<p v-if="flagged" class="mt-2 text-sm text-amber-700">{{ flagged }} slips are flagged to check.</p>
			</template>
			<template #actions>
				<div class="flex gap-2">
					<Button class="flex-1" label="Not yet" @click="confirmOpen = false" />
					<Button class="flex-1" variant="solid" label="Submit slips" :loading="busy" @click="confirmOpen = false; step('submit_slips')" />
				</div>
			</template>
		</Dialog>

		<PrintPreview v-if="printSlip" :open="!!printSlip" doctype="Salary Slip" :name="printSlip" v-bind="payslipPrint()"
			@update:open="(v) => !v && (printSlip = null)" />
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { Dialog, LoadingIndicator } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import PrintPreview from "@/components/PrintPreview.vue"
import { money, date } from "@/utils/format"
import { hr, ok, errorMessages, deskUrl, payslipPrint } from "../api"
import PageHeader from "../components/PageHeader.vue"

const props = defineProps({ name: String })
const run = ref(null)
const busy = ref(false)
const errors = ref([])
const confirmOpen = ref(false)
const printSlip = ref(null)
const paymentAccount = ref("")
let timer = null

const steps = [
	{ key: "get_employees", label: "Get employees", hint: "everyone with an active assignment" },
	{ key: "create_slips", label: "Create slips", hint: "one draft per employee" },
	{ key: "review", label: "Review drafts", hint: "the moment to catch a wrong base" },
	{ key: "submit_slips", label: "Submit slips", hint: "posts the journal to the accounts" },
	{ key: "bank_entry", label: "Bank entry", hint: "clears the payable, hits the bank" },
]
const ACTIVE = { draft: 0, employees: 1, slips: 2, submitted: 4, bank_draft: 4, paid: 4, queued: 1, failed: 1 }
const done = computed(() => run.value?.state.state === "paid")
const active = computed(() => {
	const s = run.value?.state.state
	if (s === "queued" || s === "failed") return run.value.slips.length ? 3 : 1
	return ACTIVE[s] ?? 0
})
const badge = computed(() => ({ paid: "Paid", queued: "Queued", failed: "Failed", cancelled: "Cancelled" }[run.value.state.state] || (run.value.doc.docstatus ? "Submitted" : "Draft")))
const flagged = computed(() => (run.value?.slips || []).filter((s) => s.flags.length).length)

const next = computed(() => {
	const s = run.value.state
	switch (s.state) {
		case "draft": return { step: "get_employees", button: "Get employees", title: "Get employees",
			text: "Pulls everyone with an active salary structure assignment for these dates." }
		case "employees": return { step: "create_slips", button: "Create salary slips", title: `${run.value.doc.employees.length} employees — create their slips`,
			text: "Submits the payroll entry and drafts one salary slip each. Nothing is posted yet." }
		case "slips": return { step: "submit_slips", button: "Submit salary slips", title: "Review the draft slips, then submit",
			text: flagged.value ? `${flagged.value} slips are flagged below. Fix the cause at source (leave, assignment, structure), not on the slip.` : "Nothing flagged. Open a payslip to see it as the employee will." }
		case "submitted": return { step: "bank_entry", button: "Make bank entry", title: "Slips submitted — pay them",
			text: "Creates the bank journal entry that clears Payroll Payable. Finance submits it in desk." }
		case "bank_draft": return { title: "Bank entry drafted", text: "Finance submits the journal entry in desk, and the run is paid." }
		case "paid": return { title: "Paid", text: "This run is complete. Employees can download their payslips in the HR app." }
		case "queued": return { title: "Working…", text: "HRMS is processing the slips in the background." }
		case "failed": return { step: run.value.slips.length ? "submit_slips" : "create_slips", button: "Try again", title: "Something failed", text: "Fix the error above, then try again." }
		default: return { title: s.label, text: "" }
	}
})

const n = (v) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })
const strip = (s) => String(s || "").replace(/<[^>]+>/g, " ").trim()

async function load() {
	try {
		run.value = await hr("get_payroll_entry", { name: props.name })
		paymentAccount.value = paymentAccount.value || run.value.doc.payment_account || ""
	} catch (e) {
		errors.value = errorMessages(e)
	}
	clearTimeout(timer)
	if (run.value?.state.state === "queued") timer = setTimeout(load, 4000)
}

async function step(key) {
	busy.value = true
	errors.value = []
	try {
		const r = await hr("payroll_step", { name: props.name, step: key, payment_account: key === "bank_entry" ? paymentAccount.value || undefined : undefined })
		run.value = r
		ok({ get_employees: "Employees fetched", create_slips: "Salary slips created", submit_slips: "Salary slips submitted",
			bank_entry: "Bank entry created" }[key], r.result || props.name)
		if (r.state.state === "queued") timer = setTimeout(load, 4000)
	} catch (e) {
		errors.value = errorMessages(e)
		await load()
	} finally {
		busy.value = false
	}
}

watch(() => props.name, load, { immediate: true })
onBeforeUnmount(() => clearTimeout(timer))
</script>
