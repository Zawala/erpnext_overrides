<template>
	<div class="flex h-full min-h-0 flex-col">
		<PageHeader :title="data?.employee.employee_name || name" :subtitle="headerSub" back="/people">
			<template #badge><StatusBadge v-if="data" :status="data.employee.status" /></template>
			<Button :link="deskUrl('Employee', name)" icon-left="external-link" label="Desk" variant="ghost" />
		</PageHeader>

		<div v-if="!data" class="flex flex-1 items-center justify-center text-gray-500">
			<p v-if="errors.length" class="text-red-700">{{ errors.join(" ") }}</p>
			<LoadingIndicator v-else class="h-5 w-5" />
		</div>

		<div v-else class="flex-1 overflow-y-auto">
			<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
				<!-- The links everything depends on -->
				<section class="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
					<button v-for="l in data.links" :key="l.key" class="rounded-lg border bg-white p-3 text-left transition-colors hover:border-gray-400"
						:class="[l.ok ? '' : 'border-red-200 bg-red-50', fix === l.key ? 'ring-2 ring-gray-900' : '']" @click="fixLink(l.key)">
						<div class="flex items-center gap-1.5 text-xs" :class="l.ok ? 'text-gray-500' : 'text-red-700'">
							<FeatherIcon :name="l.ok ? 'check-circle' : 'alert-circle'" class="h-3.5 w-3.5" :class="l.ok ? 'text-green-600' : 'text-red-500'" />
							{{ l.label }}
						</div>
						<div class="mt-1 truncate text-sm font-medium" :class="l.ok ? '' : 'text-red-800'">{{ l.ok ? l.value : l.missing }}</div>
					</button>
				</section>

				<div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px] items-start">
					<div class="space-y-4 min-w-0">
						<!-- Fix at source: the link fields -->
						<section id="edit" class="rounded-lg border bg-white">
							<header class="flex items-center justify-between border-b px-4 py-3">
								<div>
									<h3 class="font-semibold">Login and approvals</h3>
									<p class="text-xs text-gray-500">Department, designation and grade change through Promote or Transfer, so the history is kept.</p>
								</div>
								<Button v-if="dirty" variant="solid" label="Save" :loading="saving" @click="save" />
							</header>
							<div class="grid grid-cols-1 gap-x-6 gap-y-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
								<div v-for="f in EDIT_FIELDS" :key="f.fieldname" :id="`f-${f.fieldname}`"
									:class="fix === f.fieldname ? 'rounded ring-2 ring-amber-400 ring-offset-4' : ''">
									<Field :field="f" :doc="form" :readonly="!data.can_edit" @change="setField" />
								</div>
							</div>
						</section>

						<section class="rounded-lg border bg-white">
							<h3 class="border-b px-4 py-3 font-semibold">Job</h3>
							<dl class="grid grid-cols-2 gap-x-6 gap-y-3 p-4 text-sm sm:grid-cols-3 xl:grid-cols-4">
								<div v-for="[label, value] in job" :key="label">
									<dt class="text-gray-500">{{ label }}</dt><dd class="font-medium">{{ value || "—" }}</dd>
								</div>
							</dl>
						</section>

						<!-- Balances -->
						<section id="balances" class="rounded-lg border bg-white" :class="fix === 'balances' ? 'ring-2 ring-amber-400' : ''">
							<header class="flex items-center justify-between border-b px-4 py-3">
								<h3 class="font-semibold">Leave balance</h3>
								<Button v-if="!Object.keys(data.balances).length" label="Assign a policy" @click="$router.push('/leave?tab=assign')" />
							</header>
							<div v-if="Object.keys(data.balances).length" class="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 xl:grid-cols-5">
								<div v-for="(b, t) in data.balances" :key="t" class="rounded bg-gray-50 p-3">
									<div class="text-xs text-gray-500">{{ t }}</div>
									<div class="text-xl font-semibold tabular">{{ num(b.remaining_leaves) }}<span class="text-sm font-normal text-gray-400"> / {{ num(b.total_leaves) }}</span></div>
									<div class="text-xs text-gray-500">{{ num(b.leaves_taken) }} taken<template v-if="b.leaves_pending_approval"> · {{ num(b.leaves_pending_approval) }} pending</template></div>
									<div v-if="b.next_accrual" class="mt-0.5 text-xs text-green-700">+{{ num(b.next_accrual.days) }} on {{ date(b.next_accrual.date) }}</div>
								</div>
							</div>
							<p v-else class="px-4 py-6 text-sm text-red-700">No allocation for this period — they will see 0 days.</p>
						</section>

						<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
							<MiniList title="Leave" :rows="data.leave" :to="(r) => `/records/leave-applications/${r.name}`"
								:line="(r) => `${r.leave_type} · ${num(r.total_leave_days)} days`" :sub="(r) => `${date(r.from_date)} – ${date(r.to_date)}`" />
							<MiniList title="Expense claims" :rows="data.claims" :to="(r) => `/records/expense-claims/${r.name}`"
								:line="(r) => money(r.total_claimed_amount, r.currency)" :sub="(r) => `${r.name} · ${date(r.posting_date)}`"
								:status="(r) => (r.docstatus ? r.status : r.approval_status)" />
							<MiniList id="assignment" title="Payslips" :rows="data.slips" :to="(r) => `/records/salary-slips/${r.name}`"
								:line="(r) => money(r.net_pay, r.currency)" :sub="(r) => `${date(r.start_date)} – ${date(r.end_date)}`"
								:status="(r) => (r.docstatus ? r.status : 'Draft')" />
							<button v-if="isHR() && hasSalary" class="-mt-2 flex items-center gap-1.5 px-1 text-left text-sm text-gray-600 hover:underline"
								@click="trialOpen = true">
								<FeatherIcon name="eye" class="h-4 w-4" /> Preview this month's payslip as {{ data.employee.first_name || "they" }} will see it
							</button>
							<router-link v-if="data.slips.length" :to="`/pay-report?employee=${encodeURIComponent(name)}`"
								class="-mt-2 flex items-center gap-1.5 px-1 text-sm text-gray-600 hover:underline">
								<FeatherIcon name="file-text" class="h-4 w-4" /> Earnings, deductions and net pay this year
							</router-link>
							<section class="rounded-lg border bg-white">
								<h3 class="border-b px-4 py-3 font-semibold">History</h3>
								<ul class="divide-y">
									<li v-for="hst in data.history" :key="hst.name" class="px-4 py-2.5 text-sm">
										<router-link :to="`/records/${hst.doctype === 'Employee Promotion' ? 'promotions' : 'transfers'}/${hst.name}`" class="hover:underline">
											<span class="font-medium">{{ hst.doctype.replace("Employee ", "") }}</span> · {{ date(hst.date) }}
											<span v-if="!hst.docstatus" class="text-amber-700">(draft)</span>
										</router-link>
										<div v-for="c in hst.changes" :key="c.property" class="text-gray-600">{{ c.property }}: {{ c.current || "—" }} → <b>{{ c.new }}</b></div>
									</li>
									<li v-if="!data.history.length" class="px-4 py-6 text-center text-gray-500">No promotions or transfers yet.</li>
								</ul>
							</section>
						</div>
					</div>

					<!-- Right rail: lifecycle -->
					<aside class="space-y-4 xl:sticky xl:top-4">
						<section class="rounded-lg border bg-white p-4 space-y-2">
							<h3 class="font-semibold">Next step</h3>
							<p class="text-sm text-gray-500">These change the record for you, on the date, and keep the old value.</p>
							<Button class="w-full" icon-left="trending-up" label="Promote" :disabled="!active" @click="$router.push(`/people/${name}/promotion`)" />
							<Button class="w-full" icon-left="shuffle" label="Transfer" :disabled="!active" @click="$router.push(`/people/${name}/transfer`)" />
							<Button v-if="!data.separation" class="w-full" theme="red" variant="subtle" icon-left="log-out" label="Start exit"
								:disabled="!active" @click="$router.push(`/people/${name}/separation`)" />
							<template v-else>
								<router-link :to="`/records/separations/${data.separation.name}`" class="block rounded border px-3 py-2 text-sm hover:bg-gray-50">
									Exit {{ data.separation.boarding_status?.toLowerCase() }} · from {{ date(data.separation.boarding_begins_on) }}
								</router-link>
								<div v-if="active && data.can_edit" class="space-y-2 rounded border border-red-200 bg-red-50 p-3">
									<label class="block text-sm text-red-900">Relieving date
										<input v-model="relieving" type="date" class="form-input mt-1 w-full" /></label>
									<Button class="w-full" theme="red" variant="solid" label="Mark as Left" :loading="saving" @click="markLeft" />
									<p class="text-xs text-red-800">Stops payroll and leave for them.</p>
								</div>
							</template>
						</section>
						<section class="rounded-lg border bg-white p-4 text-sm space-y-1">
							<div class="flex justify-between"><span class="text-gray-500">Joined</span><span>{{ date(data.employee.date_of_joining) }}</span></div>
							<div class="flex justify-between"><span class="text-gray-500">Born</span><span>{{ date(data.employee.date_of_birth) }}</span></div>
							<div class="flex justify-between"><span class="text-gray-500">Mobile</span><span>{{ data.employee.cell_number || "—" }}</span></div>
							<div v-if="data.employee.relieving_date" class="flex justify-between"><span class="text-gray-500">Relieved</span><span>{{ date(data.employee.relieving_date) }}</span></div>
						</section>
					</aside>
				</div>
			</div>
		</div>

		<PrintPreview v-if="trialOpen" v-model:open="trialOpen" doctype="Salary Slip" :name="name" :trial="trial" v-bind="payslipPrint()" />
	</div>
</template>

<script setup>
import { computed, h, nextTick, reactive, ref, watch } from "vue"
import { useRoute, useRouter, RouterLink } from "vue-router"
import { LoadingIndicator, call } from "frappe-ui"
import Field from "@/components/Field.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { money, date, today } from "@/utils/format"
import PrintPreview from "@/components/PrintPreview.vue"
import { hr, ok, fail, errorMessages, deskUrl, isHR, payslipPrint } from "../api"
import PageHeader from "../components/PageHeader.vue"

const props = defineProps({ name: String })
const route = useRoute()
const router = useRouter()
const data = ref(null)
const errors = ref([])
const form = reactive({})
const dirty = ref(false)
const saving = ref(false)
const relieving = ref(today())
const trialOpen = ref(false)
const hasSalary = computed(() => !!data.value?.links.find((l) => l.key === "assignment")?.ok)
const trial = computed(() => ({
	method: "erp_overrides.api.hr.preview_payslip",
	args: { employee: props.name },
	note: `Trial for ${new Date().toLocaleDateString(undefined, { month: "long", year: "numeric" })} from the salary assignment: a full month, nothing saved`,
}))
const fix = computed(() => route.query.fix)

const EDIT_FIELDS = [
	{ fieldname: "user_id", label: "User ID (login)", type: "Link", options: "User", help: "What the HR app checks. Blank = “it won't let me log in”." },
	{ fieldname: "reports_to", label: "Reports to", type: "Link", options: "Employee", help: "Builds the approval chain and the org chart." },
	{ fieldname: "leave_approver", label: "Leave approver", type: "Link", options: "User", filters: () => ({ enabled: 1 }) },
	{ fieldname: "expense_approver", label: "Expense approver", type: "Link", options: "User", filters: () => ({ enabled: 1 }) },
	{ fieldname: "holiday_list", label: "Holiday list", type: "Link", options: "Holiday List", help: "Blank uses the company's list." },
	{ fieldname: "company_email", label: "Company email", type: "Data", inputType: "email", help: "Payslips go here." },
	{ fieldname: "cell_number", label: "Mobile", type: "Data", inputType: "tel" },
]

const active = computed(() => data.value?.employee.status === "Active")
const headerSub = computed(() => {
	const e = data.value?.employee
	return e ? [e.designation, e.department, props.name].filter(Boolean).join(" · ") : props.name
})
const job = computed(() => {
	const e = data.value.employee
	return [["Company", e.company], ["Department", e.department], ["Designation", e.designation], ["Grade", e.grade],
		["Branch", e.branch], ["Employment type", e.employment_type], ["Reports to", e.reports_to_name],
		["CTC", e.ctc ? money(e.ctc, e.salary_currency) : ""]]
})
const num = (v) => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })

function setField(fieldname, value) {
	form[fieldname] = value
	dirty.value = true
}

function fixLink(key) {
	if (key === "assignment") {
		return router.push(`/salaries?employee=${encodeURIComponent(props.name)}`)
	}
	const target = key === "allocation" ? "balances" : `f-${key}`
	document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "center" })
}

async function load() {
	errors.value = []
	try {
		data.value = await hr("get_employee", { name: props.name })
		for (const f of EDIT_FIELDS) form[f.fieldname] = data.value.employee[f.fieldname] || ""
		dirty.value = false
		// arriving from a health-check Fix: bring the field (or section) into view
		const target = { balances: "balances", assignment: "assignment" }[fix.value] || `f-${fix.value}`
		if (fix.value) nextTick(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "center" }))
	} catch (e) {
		errors.value = errorMessages(e)
	}
}

async function save() {
	saving.value = true
	try {
		const changes = Object.fromEntries(EDIT_FIELDS.map((f) => [f.fieldname, form[f.fieldname] || null])
			.filter(([k, v]) => (data.value.employee[k] || null) !== v))
		await call("frappe.client.set_value", { doctype: "Employee", name: props.name, fieldname: changes })
		ok("Saved", Object.keys(changes).join(", "))
		await load()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

async function markLeft() {
	saving.value = true
	try {
		await hr("mark_left", { employee: props.name, relieving_date: relieving.value })
		ok("Marked as Left", data.value.employee.employee_name)
		await load()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

const MiniList = (p) =>
	h("section", { class: "rounded-lg border bg-white", id: p.id }, [
		h("h3", { class: "border-b px-4 py-3 font-semibold" }, p.title),
		h("ul", { class: "divide-y" }, p.rows.length
			? p.rows.map((r) => h("li", {}, h(RouterLink, { to: p.to(r), class: "flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-gray-50" }, () => [
				h("div", { class: "min-w-0" }, [h("div", { class: "truncate font-medium" }, p.line(r)), h("div", { class: "truncate text-gray-500" }, p.sub(r))]),
				h(StatusBadge, { status: p.status ? p.status(r) : r.docstatus === 0 ? "Draft" : r.status, size: "sm" }),
			])))
			: [h("li", { class: "px-4 py-6 text-center text-sm text-gray-500" }, "Nothing yet.")]),
	])
MiniList.props = ["title", "rows", "to", "line", "sub", "status", "id"]

watch(() => props.name, load, { immediate: true })
</script>
