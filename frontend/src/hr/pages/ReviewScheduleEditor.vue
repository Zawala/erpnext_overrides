<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="isNew ? 'New review schedule' : doc?.title || 'Review schedule'" subtitle="Who is reviewed, how often and with which form" back="/reviews">
			<Button variant="solid" label="Save" :loading="saving" :disabled="!doc" @click="save" />
		</PageHeader>

		<div v-if="!doc" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto grid w-full max-w-[1600px] gap-4 p-4 lg:p-6 xl:grid-cols-[1fr_440px]">
			<div class="min-w-0 space-y-4">
				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
					<p v-for="e in errors" :key="e">{{ e }}</p>
				</div>
				<section class="grid gap-3 rounded-lg border bg-white p-4 sm:grid-cols-2">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Title <span class="text-red-500">*</span></span>
						<input v-model="doc.title" class="form-input w-full" :disabled="!isNew" placeholder="e.g. Sales team check-ins" /></label>
					<label class="flex items-center gap-2 self-end pb-2 text-sm"><input v-model="doc.active" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" />
						Active <span class="text-gray-500">— untick to pause; open reviews stay open</span></label>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Review form <span class="text-red-500">*</span></span>
						<select v-model="doc.review_form" class="form-select w-full"><option v-for="f in forms" :key="f" :value="f">{{ f }}</option></select></label>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">How often</span>
						<select v-model="doc.frequency" class="form-select w-full"><option v-for="f in FREQ" :key="f">{{ f }}</option></select></label>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">First period starts <span class="text-red-500">*</span></span>
						<input v-model="doc.first_period_start" type="date" class="form-input w-full" />
						<span class="mt-1 block text-xs text-gray-500">Periods run back to back from here. A review opens the day after each period ends.</span></label>
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Days to complete</span>
						<input v-model.number="doc.window_days" type="number" min="1" max="30" class="form-input w-full" />
						<span class="mt-1 block text-xs text-gray-500">Reminders go two days before the end.</span></label>
				</section>

				<section class="grid gap-3 rounded-lg border bg-white p-4 sm:grid-cols-3">
					<h2 class="font-semibold sm:col-span-3">Who is reviewed</h2>
					<label v-for="f in FILTERS" :key="f.field" class="block"><span class="mb-1.5 block text-sm text-gray-600">{{ f.label }}</span>
						<LinkField v-model="doc[f.field]" :doctype="f.doctype" :placeholder="`Any ${f.label.toLowerCase()}`" /></label>
					<div class="sm:col-span-3">
						<div class="mb-1.5 text-sm text-gray-600">Only these people <span class="text-gray-400">(leave empty for everyone matching the filters)</span></div>
						<div class="flex flex-wrap gap-1.5">
							<span v-for="(e, i) in doc.employees" :key="e.employee" class="flex items-center gap-1 rounded-full border bg-gray-50 px-2.5 py-0.5 text-sm">
								{{ e.employee_name || e.employee }}
								<button type="button" class="text-gray-400 hover:text-gray-700" aria-label="Remove" @click="doc.employees.splice(i, 1)">×</button>
							</span>
							<div class="w-64"><LinkField v-model="adding" doctype="Employee" :filters="{ status: 'Active' }" placeholder="Add a person" /></div>
						</div>
					</div>
					<label class="block sm:col-span-3"><span class="mb-1.5 block text-sm text-gray-600">Overdue summary goes to</span>
						<textarea v-model="doc.hr_recipients" rows="2" class="form-textarea w-full" placeholder="Email addresses; empty = every HR Manager" /></label>
				</section>
			</div>

			<aside class="space-y-4 xl:sticky xl:top-4 xl:self-start">
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Next windows</h3>
					<p v-if="!preview?.windows.length" class="px-4 py-3 text-sm text-gray-500">Pick the first period's start.</p>
					<div v-for="w in preview?.windows || []" :key="w.period_start" class="border-t px-4 py-2 text-sm first-of-type:border-t-0">
						<div class="font-medium">{{ date(w.period_start) }} – {{ date(w.period_end) }}</div>
						<div class="text-xs text-gray-500">Opens {{ date(w.opens_on) }}, due {{ date(w.due_on) }}</div>
					</div>
				</section>
				<section class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">People · {{ preview?.people.length || 0 }}</h3>
					<p v-if="preview?.no_manager.length" class="border-b bg-amber-50 px-4 py-2 text-sm text-amber-900">
						No manager, so no review: {{ preview.no_manager.join(", ") }}. Set their Reports To on the employee page.</p>
					<ul class="max-h-96 divide-y overflow-y-auto">
						<li v-for="p in preview?.people || []" :key="p.name" class="flex items-center gap-2 px-4 py-2 text-sm">
							<span class="min-w-0 flex-1 truncate">{{ p.employee_name }}</span>
							<span class="truncate text-xs" :class="p.manager ? 'text-gray-500' : 'text-amber-700'">{{ p.manager_name || "no manager" }}</span>
						</li>
					</ul>
				</section>
			</aside>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { LoadingIndicator, call, debounce } from "frappe-ui"
import { boot } from "@/boot"
import { date, today } from "@/utils/format"
import LinkField from "@/components/LinkField.vue"
import { errorMessages, ok } from "../api"
import PageHeader from "../components/PageHeader.vue"

const FREQ = ["Every 2 weeks", "Weekly", "Monthly"]
const FILTERS = [
	{ field: "department", label: "Department", doctype: "Department" },
	{ field: "branch", label: "Branch", doctype: "Branch" },
	{ field: "designation", label: "Designation", doctype: "Designation" },
]
const props = defineProps({ name: String })
const router = useRouter()
const isNew = computed(() => props.name === "new")
const doc = ref(null)
const forms = ref([])
const preview = ref(null)
const errors = ref([])
const saving = ref(false)
const adding = ref("")

call("frappe.client.get_list", { doctype: "Review Form", filters: { active: 1 }, pluck: "name", limit_page_length: 100 })
	.then((f) => (forms.value = f.map((x) => x.name || x))).catch(() => {})

async function load() {
	errors.value = []
	doc.value = isNew.value
		? { doctype: "Review Schedule", title: "", active: 1, review_form: "Bi-weekly check-in", frequency: "Every 2 weeks",
			first_period_start: today(), window_days: 5, company: boot.company, employees: [] }
		: await call("frappe.client.get", { doctype: "Review Schedule", name: props.name })
}
watch(() => props.name, load, { immediate: true })

const refresh = debounce(async () => {
	try {
		preview.value = await call("erp_overrides.api.reviews.preview_schedule", { doc: doc.value })
	} catch (e) {
		errors.value = errorMessages(e)
	}
}, 400)
watch(() => doc.value && [doc.value.frequency, doc.value.first_period_start, doc.value.window_days, doc.value.department,
	doc.value.branch, doc.value.designation, doc.value.employees.map((e) => e.employee).join()], refresh, { immediate: true })

watch(adding, async (emp) => {
	if (!emp) return
	if (!doc.value.employees.some((e) => e.employee === emp)) {
		const name = await call("frappe.client.get_value", { doctype: "Employee", filters: emp, fieldname: "employee_name" }).catch(() => null)
		doc.value.employees.push({ doctype: "Review Schedule Employee", employee: emp, employee_name: name?.employee_name })
	}
	adding.value = ""
})

async function save() {
	saving.value = true
	errors.value = []
	try {
		const saved = await call(isNew.value ? "frappe.client.insert" : "frappe.client.save", { doc: doc.value })
		ok("Saved", saved.name)
		if (isNew.value) router.replace(`/review-schedules/${encodeURIComponent(saved.name)}`)
		else doc.value = saved
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		saving.value = false
	}
}
</script>
