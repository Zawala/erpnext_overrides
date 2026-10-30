<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Payroll" subtitle="Setup once; the monthly run is four clicks">
			<Button class="hidden sm:inline-flex" icon-left="edit-3" label="Salaries" @click="$router.push('/salaries')" />
			<Button class="hidden sm:inline-flex" icon-left="file-text" label="Pay report" @click="$router.push('/pay-report')" />
			<Button v-if="current" variant="solid" icon-left="play" :label="`Open ${monthLabel} run`" @click="$router.push(`/payroll/${current.name}`)" />
			<Button v-else-if="overview" variant="solid" icon-left="plus" :label="`Start ${monthLabel} payroll`"
				:disabled="!overview.payroll_payable_account" @click="startOpen = true" />
		</PageHeader>

		<div v-if="!overview" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<div v-if="!overview.payroll_payable_account" class="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
				<FeatherIcon name="x-octagon" class="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
				<div>{{ overview.company }} has no Default Payroll Payable Account, so no payroll entry can be created.
					<a :href="deskUrl('Company', overview.company)" target="_blank" class="underline">Set it on the company ↗</a></div>
			</div>

			<div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_420px] items-start">
				<!-- Readiness -->
				<section class="rounded-lg border bg-white">
					<header class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
						<div>
							<h3 class="font-semibold">Who gets paid for {{ monthLabel }}</h3>
							<p class="text-sm text-gray-500">No submitted assignment means no slip. A structure with no components pays zero.</p>
						</div>
						<div v-if="readiness" class="text-right">
							<div class="text-xl font-semibold tabular" :class="readiness.ready < readiness.total ? 'text-amber-600' : 'text-green-700'">
								{{ readiness.ready }} / {{ readiness.total }}
							</div>
							<div class="text-xs text-gray-500">ready</div>
						</div>
					</header>
					<div v-if="!readiness" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<ul v-else class="divide-y">
						<li v-for="r in sortedReadiness" :key="r.employee" class="flex items-center gap-3 px-4 py-2.5">
							<FeatherIcon :name="r.problem ? 'alert-circle' : 'check-circle'" class="h-4 w-4 shrink-0"
								:class="r.problem ? 'text-red-500' : 'text-green-600'" />
							<router-link :to="`/people/${r.employee}`" class="min-w-0 flex-1 hover:underline">
								<div class="truncate font-medium">{{ r.employee_name }}</div>
								<div class="truncate text-sm" :class="r.problem ? 'text-red-700' : 'text-gray-500'">
									{{ r.problem || `${r.salary_structure} · base ${money(r.base, overview.currency)}` }}
								</div>
							</router-link>
							<Button v-if="r.problem" size="sm" label="Fix" @click="fixAssignment(r)" />
						</li>
					</ul>
				</section>

				<!-- Runs -->
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Payroll runs</h3>
					<ul class="divide-y">
						<li v-for="e in overview.entries" :key="e.name">
							<router-link :to="`/payroll/${e.name}`" class="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-gray-50">
								<div class="min-w-0">
									<div class="font-medium">{{ date(e.start_date) }} – {{ date(e.end_date) }}</div>
									<div class="truncate text-sm text-gray-500">{{ e.name }} · {{ e.number_of_employees || 0 }} employees</div>
								</div>
								<span class="shrink-0 text-right text-sm" :class="e.state === 'paid' ? 'text-green-700' : 'text-gray-700'">{{ e.label }}</span>
							</router-link>
						</li>
						<li v-if="!overview.entries.length" class="px-4 py-6 text-center text-sm text-gray-500">Payroll has never been run.</li>
					</ul>
				</section>
			</div>

		</div>

		<Dialog v-model="startOpen" :options="{ title: `Start ${monthLabel} payroll`, size: 'lg' }">
			<template #body-content>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<label><span class="mb-1.5 block text-sm text-gray-600">From</span><input v-model="form.start_date" type="date" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">To</span><input v-model="form.end_date" type="date" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Posting date</span><input v-model="form.posting_date" type="date" class="form-input w-full" /></label>
					<label class="sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Pay from (bank account)</span>
						<LinkField v-model="form.payment_account" doctype="Account"
							:filters="{ account_type: ['in', ['Bank', 'Cash']], is_group: 0, company: overview.company }" />
					</label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Department (optional)</span>
						<LinkField v-model="form.department" doctype="Department" placeholder="Everyone" /></label>
				</div>
				<p class="mt-3 text-sm text-gray-500">
					Monthly, {{ overview?.currency }}, posted to {{ overview?.payroll_payable_account || "—" }}.
					Payment days come from approved leave — check leave is up to date first.
				</p>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Create payroll entry" :loading="creating" @click="create" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { Dialog, LoadingIndicator } from "frappe-ui"
import LinkField from "@/components/LinkField.vue"
import { money, date, today } from "@/utils/format"
import { hr, ok, fail, deskUrl } from "../api"
import PageHeader from "../components/PageHeader.vue"

const router = useRouter()
const overview = ref(null)
const readiness = ref(null)
const startOpen = ref(false)
const creating = ref(false)
const form = reactive({ start_date: "", end_date: "", posting_date: today(), payment_account: "", department: "" })

const monthLabel = computed(() =>
	overview.value ? new Date(overview.value.start_date + "T00:00:00").toLocaleDateString(undefined, { month: "long", year: "numeric" }) : ""
)
const current = computed(() => overview.value?.entries.find((e) => e.start_date === overview.value.start_date))
const sortedReadiness = computed(() => [...(readiness.value?.rows || [])].sort((a, b) => !!b.problem - !!a.problem))

// A draft assignment is finished on the record; a missing or zero salary is set on Salaries.
function fixAssignment(r) {
	if (r.problem?.includes("draft")) return window.open(deskUrl("Salary Structure Assignment", r.assignment), "_blank")
	router.push(`/salaries?employee=${encodeURIComponent(r.employee)}`)
}

async function load() {
	try {
		overview.value = await hr("get_payroll_overview")
		Object.assign(form, { start_date: overview.value.start_date, end_date: overview.value.end_date })
		readiness.value = await hr("get_payroll_readiness", { start_date: overview.value.start_date, end_date: overview.value.end_date })
	} catch (e) {
		fail(e, "Could not load payroll")
	}
}

async function create() {
	creating.value = true
	try {
		const name = await hr("new_payroll_entry", { ...form, payment_account: form.payment_account || undefined, department: form.department || undefined })
		ok("Payroll entry created", name)
		router.push(`/payroll/${name}`)
	} catch (e) {
		fail(e)
	} finally {
		creating.value = false
	}
}

load()
</script>
