<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Leave" subtitle="Six steps, and the order is not optional">
			<Button icon-left="list" label="Applications" @click="$router.push('/records/leave-applications')" />
			<Button class="hidden sm:inline-flex" icon-left="pie-chart" label="Balances" @click="$router.push('/balances')" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-6">
			<!-- The six steps of leave setup -->
			<ol class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
				<li v-for="(s, i) in setup?.steps || placeholders" :key="s.key">
					<component :is="s.desk_url ? 'a' : 'button'" :href="s.desk_url" :target="s.desk_url ? '_blank' : undefined"
						class="flex h-full w-full flex-col justify-start rounded-lg border bg-white p-3 text-left transition-colors hover:border-gray-400"
						:class="s.done === false ? 'border-red-200' : ''" @click="!s.desk_url && jump(s.key)">
						<div class="flex items-center justify-between">
							<span class="text-sm font-semibold text-gray-400">{{ i + 1 }}</span>
							<FeatherIcon v-if="s.done !== undefined" :name="s.done ? 'check-circle' : 'alert-circle'" class="h-4 w-4"
								:class="s.done ? 'text-green-600' : 'text-red-500'" />
						</div>
						<div class="mt-1 font-medium">{{ s.label }}</div>
						<div class="text-xs text-gray-500">{{ s.hint }}<template v-if="s.count"> · {{ s.count }}</template></div>
					</component>
				</li>
			</ol>
			<p class="-mt-3 text-sm text-gray-500">
				Each step needs the one before it: no allocation without a policy and a period, no application without an allocation.
			</p>

			<Chips v-model="tab" :options="[{ value: 'setup', label: 'Setup' }, { value: 'assign', label: 'Assign a policy' }]" />

			<div v-if="!setup" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>

			<!-- Setup -->
			<div v-else-if="tab === 'setup'" class="grid grid-cols-1 gap-4 xl:grid-cols-2 items-start">
				<section id="holiday_list" class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h3 class="font-semibold">1 · Holiday lists</h3>
						<Button :link="deskUrl('Holiday List')" variant="ghost" icon-left="external-link" label="Edit in desk" />
					</header>
					<ul class="divide-y">
						<li v-for="h in setup.holiday_lists" :key="h.name" class="flex items-center justify-between px-4 py-2.5 text-sm">
							<div>
								<div class="font-medium">{{ h.name }}</div>
								<div class="text-gray-500">{{ date(h.from_date) }} – {{ date(h.to_date) }}<template v-if="h.weekly_off"> · {{ h.weekly_off }} off</template></div>
							</div>
							<span class="tabular" :class="h.total_holidays ? '' : 'text-red-600'">{{ h.total_holidays || 0 }} days</span>
						</li>
					</ul>
				</section>

				<section id="leave_period" class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h3 class="font-semibold">2 · Leave periods</h3>
						<Button icon-left="plus" label="New period" @click="periodOpen = true" />
					</header>
					<ul class="divide-y">
						<li v-for="p in setup.periods" :key="p.name" class="flex items-center justify-between px-4 py-2.5 text-sm">
							<div>
								<div class="font-medium">{{ date(p.from_date) }} – {{ date(p.to_date) }}</div>
								<div class="text-gray-500">{{ p.name }}</div>
							</div>
							<StatusBadge :status="p.name === setup.active_period ? 'Current' : p.is_active ? 'Active' : 'Inactive'" size="sm" />
						</li>
						<li v-if="!setup.periods.length" class="px-4 py-6 text-center text-sm text-red-600">
							No leave period — create this year's first.
						</li>
					</ul>
				</section>

				<section id="leave_policy" class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h3 class="font-semibold">3 · Leave policies</h3>
						<Button icon-left="plus" label="New policy" @click="openPolicy" />
					</header>
					<ul class="divide-y">
						<li v-for="p in setup.policies" :key="p.name" class="px-4 py-2.5 text-sm">
							<div class="flex items-center justify-between">
								<div class="font-medium">{{ p.title }}</div>
								<StatusBadge :status="p.docstatus ? 'Submitted' : 'Draft'" size="sm" />
							</div>
							<div class="mt-1 text-gray-500">
								{{ p.details.map((d) => `${d.leave_type} ${d.annual_allocation}`).join(" · ") }}
							</div>
						</li>
						<li v-if="!setup.policies.length" class="px-4 py-6 text-center text-sm text-red-600">
							No policy — build one per grade, e.g. Casual 12, Sick 10, Privilege 21.
						</li>
					</ul>
				</section>

				<section class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<div>
							<h3 class="font-semibold">Leave types</h3>
							<p class="text-xs text-gray-500">These rules apply to everybody who gets the type. Decide once.</p>
						</div>
						<Button icon-left="plus" label="New leave type" @click="editType(null)" />
					</header>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="bg-gray-50">
								<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
									<th class="px-4 py-2 font-medium">Type</th>
									<th class="px-2 py-2 text-right font-medium">Max</th>
									<th class="px-2 py-2 font-medium">Rules</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="t in setup.leave_types" :key="t.name" class="cursor-pointer border-t align-top hover:bg-gray-50" @click="editType(t.name)">
									<td class="px-4 py-2 font-medium">{{ t.name }}</td>
									<td class="whitespace-nowrap px-2 py-2 text-right tabular">{{ Number(t.max_leaves_allowed) ? t.max_leaves_allowed : "no cap" }}</td>
									<td class="px-2 py-2">
										<div class="flex flex-wrap gap-1">
											<span v-for="r in rules(t)" :key="r.label" class="rounded px-1.5 py-0.5 text-xs"
												:class="r.warn ? 'bg-amber-50 text-amber-800' : 'bg-gray-100 text-gray-700'" :title="r.title">{{ r.label }}</span>
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
			</div>

			<!-- Assign a policy: allocations in bulk (step 4) -->
			<section v-else id="allocation" class="rounded-lg border bg-white">
				<header class="border-b px-4 py-3">
					<h3 class="font-semibold">4 · Assign a leave policy</h3>
					<p class="text-sm text-gray-500">
						One assignment per person creates every allocation in the policy. You never type a balance by hand.
					</p>
				</header>
				<div class="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 xl:grid-cols-4">
					<label>
						<span class="mb-1.5 block text-sm text-gray-600">Policy</span>
						<select v-model="assign.policy" class="form-select w-full">
							<option value="" disabled>Pick a policy</option>
							<option v-for="p in submittedPolicies" :key="p.name" :value="p.name">{{ p.title }}</option>
						</select>
					</label>
					<label>
						<span class="mb-1.5 block text-sm text-gray-600">Leave period</span>
						<select v-model="assign.period" class="form-select w-full">
							<option value="" disabled>Pick a period</option>
							<option v-for="p in setup.periods" :key="p.name" :value="p.name">{{ date(p.from_date) }} – {{ date(p.to_date) }}</option>
						</select>
					</label>
					<label>
						<span class="mb-1.5 block text-sm text-gray-600">Department</span>
						<LinkField v-model="assign.department" doctype="Department" placeholder="Everyone" />
					</label>
					<label class="flex items-center gap-2 self-end pb-1.5 text-sm text-gray-700">
						<input v-model="assign.carry" type="checkbox" class="form-checkbox" /> Carry forward unused days from last period
					</label>
				</div>
				<p v-if="!submittedPolicies.length || !setup.periods.length" class="px-4 pb-4 text-sm text-red-600">
					You need a leave period and a submitted policy first (steps 2 and 3).
				</p>

				<template v-if="candidates.length">
					<div class="flex items-center justify-between border-t px-4 py-2 text-sm">
						<label class="flex items-center gap-2"><input type="checkbox" class="form-checkbox" :checked="allPicked" @change="pickAll($event.target.checked)" />
							{{ picked.size }} of {{ eligible.length }} selected</label>
						<span class="text-gray-500">{{ candidates.length - eligible.length }} already have a policy for this period</span>
					</div>
					<ul class="max-h-[50vh] divide-y overflow-y-auto border-t">
						<li v-for="c in shown" :key="c.name">
							<label class="flex items-center gap-3 px-4 py-2" :class="c.current_policy ? 'opacity-60' : 'cursor-pointer hover:bg-gray-50'">
								<input type="checkbox" class="form-checkbox" :disabled="!!c.current_policy" :checked="picked.has(c.name)"
									@change="toggle(c.name)" />
								<div class="min-w-0 flex-1">
									<div class="font-medium">{{ c.employee_name }}</div>
									<div class="text-xs text-gray-500">{{ [c.department, c.designation, c.grade].filter(Boolean).join(" · ") }}</div>
								</div>
								<span v-if="c.current_policy" class="text-xs text-gray-500">{{ c.current_policy }}</span>
							</label>
						</li>
					</ul>
				</template>
				<footer class="flex justify-end border-t px-4 py-3">
					<Button variant="solid" :label="`Assign to ${picked.size}`" :disabled="!picked.size || !assign.policy"
						:loading="assigning" @click="runAssign" />
				</footer>
			</section>
		</div>

		<LeaveTypeDialog :open="typeOpen" :name="typeName" @close="typeOpen = false" @saved="load" />

		<!-- New leave period -->
		<Dialog v-model="periodOpen" :options="{ title: 'New leave period', size: 'md' }">
			<template #body-content>
				<div class="grid grid-cols-2 gap-3">
					<label><span class="mb-1.5 block text-sm text-gray-600">From</span><input v-model="period.from_date" type="date" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">To</span><input v-model="period.to_date" type="date" class="form-input w-full" /></label>
				</div>
				<p class="mt-3 text-sm text-gray-500">The year leave is counted in. Usually 1 January to 31 December.</p>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Create period" :loading="saving" @click="createPeriod" />
			</template>
		</Dialog>

		<!-- New leave policy -->
		<Dialog v-model="policyOpen" :options="{ title: 'New leave policy', size: 'lg' }">
			<template #body-content>
				<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Name</span>
					<input v-model="policy.title" class="form-input w-full" placeholder="e.g. Staff 2026" /></label>
				<div class="mt-4 text-sm text-gray-600">Days per year</div>
				<div class="mt-1.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
					<label v-for="t in policyTypes" :key="t.name" class="flex items-center gap-3 rounded border px-3 py-2">
						<span class="flex-1 text-sm">{{ t.name }}<span v-if="Number(t.max_leaves_allowed)" class="text-gray-400"> (max {{ t.max_leaves_allowed }})</span></span>
						<input v-model.number="policy.days[t.name]" type="number" min="0" step="0.5" class="form-input w-20 text-right tabular" />
					</label>
				</div>
				<p class="mt-3 text-xs text-gray-500">Saved and submitted straight away — a draft policy cannot be assigned.</p>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Create policy" :loading="saving" @click="createPolicy" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Dialog, LoadingIndicator, call } from "frappe-ui"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import StatusBadge from "@/components/StatusBadge.vue"
import { date } from "@/utils/format"
import { hr, ok, fail, deskUrl } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import LeaveTypeDialog from "../components/LeaveTypeDialog.vue"

const route = useRoute()
const router = useRouter()
const setup = ref(null)
const tab = ref(route.query.tab === "assign" ? "assign" : "setup")
watch(tab, (t) => router.replace({ query: { ...route.query, tab: t } }))

const placeholders = ["Holiday List", "Leave Period", "Leave Policy", "Leave Allocation", "Leave Application", "Leave Ledger"].map((label) => ({ key: label, label, hint: "" }))

function jump(key) {
	if (key === "application") return router.push("/records/leave-applications")
	tab.value = key === "allocation" ? "assign" : "setup"
	nextTick(() => document.getElementById(key)?.scrollIntoView({ behavior: "smooth", block: "start" }))
}

const rules = (t) => [
	t.include_holiday && { label: "Holidays count as leave", warn: true, title: "A public holiday inside a request is charged as leave" },
	t.is_carry_forward && { label: `Carry forward${Number(t.maximum_carry_forwarded_leaves) ? ` ≤ ${t.maximum_carry_forwarded_leaves}` : " (no cap)"}`,
		warn: !Number(t.maximum_carry_forwarded_leaves) },
	t.is_carry_forward && Number(t.expire_carry_forwarded_leaves_after_days) && { label: `Carried days expire after ${t.expire_carry_forwarded_leaves_after_days}d` },
	t.is_earned_leave && { label: `Earned ${String(t.earned_leave_frequency || "").toLowerCase()}, ${String(t.allocate_on_day || "").toLowerCase()}`,
		title: "Allocated automatically by the scheduler" },
	t.allow_encashment && { label: "Encashable" },
	t.allow_negative && { label: "Can go negative", warn: true },
	t.is_lwp && { label: "Unpaid" },
	Number(t.max_continuous_days_allowed) && { label: `Max ${t.max_continuous_days_allowed} days in a row` },
].filter(Boolean)

async function load() {
	try {
		setup.value = await hr("get_leave_setup")
		if (!assign.period) assign.period = setup.value.active_period || setup.value.periods[0]?.name || ""
	} catch (e) {
		fail(e, "Could not load leave setup")
	}
}

// Leave types
const typeOpen = ref(false)
const typeName = ref(null)
function editType(name) {
	typeName.value = name
	typeOpen.value = true
}

// New period
const periodOpen = ref(false)
const saving = ref(false)
const year = new Date().getFullYear()
const period = reactive({ from_date: `${year}-01-01`, to_date: `${year}-12-31` })
async function createPeriod() {
	saving.value = true
	try {
		await call("frappe.client.insert", { doc: { doctype: "Leave Period", ...period, is_active: 1, company: boot.company } })
		ok("Leave period created")
		periodOpen.value = false
		await load()
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

// New policy
const policyOpen = ref(false)
const policy = reactive({ title: "", days: {} })
const policyTypes = computed(() => (setup.value?.leave_types || []).filter((t) => !t.is_lwp && !t.is_compensatory))
function openPolicy() {
	policy.title = `Staff ${year}`
	policy.days = Object.fromEntries(policyTypes.value.map((t) => [t.name, 0]))
	policyOpen.value = true
}
async function createPolicy() {
	saving.value = true
	try {
		const name = await hr("create_leave_policy", { title: policy.title, allocations: policy.days })
		ok("Leave policy created", name)
		policyOpen.value = false
		await load()
		assign.policy = name
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

// Assign
const assign = reactive({ policy: "", period: "", department: "", carry: false })
const candidates = ref([])
const picked = ref(new Set())
const assigning = ref(false)
const submittedPolicies = computed(() => (setup.value?.policies || []).filter((p) => p.docstatus === 1))
const shown = computed(() => candidates.value.filter((c) => !assign.department || c.department === assign.department))
const eligible = computed(() => shown.value.filter((c) => !c.current_policy))
const allPicked = computed(() => eligible.value.length > 0 && eligible.value.every((c) => picked.value.has(c.name)))
function pickAll(on) {
	picked.value = new Set(on ? eligible.value.map((c) => c.name) : [])
}
function toggle(name) {
	const s = new Set(picked.value)
	s.has(name) ? s.delete(name) : s.add(name)
	picked.value = s
}
async function loadCandidates() {
	if (!assign.period) return (candidates.value = [])
	candidates.value = await hr("get_policy_candidates", { leave_period: assign.period })
	pickAll(true)
}
watch(() => assign.period, loadCandidates)
watch(() => assign.department, () => pickAll(true))
watch(submittedPolicies, (list) => {
	if (!assign.policy && list.length === 1) assign.policy = list[0].name
})

async function runAssign() {
	assigning.value = true
	try {
		const r = await hr("assign_policy", {
			leave_policy: assign.policy, leave_period: assign.period, employees: [...picked.value], carry_forward: assign.carry ? 1 : 0,
		})
		ok(`Assigned to ${r.created}`, r.failed ? `${r.failed} failed — see the Error Log in desk` : "Balances are ready")
		await Promise.all([load(), loadCandidates()])
	} catch (e) {
		fail(e)
	} finally {
		assigning.value = false
	}
}

load()
</script>
