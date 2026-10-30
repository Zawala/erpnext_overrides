<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="review ? review.employee_name : 'Review'" :subtitle="subtitle" :back="boot.is_hr && review?.role === 'hr' ? '/reviews' : '/my-reviews'">
			<template #badge><span v-if="review" class="rounded px-1.5 py-0.5 text-xs" :class="statusTheme">{{ statusLabel }}</span></template>
			<Button v-if="review?.role === 'hr' && review.status === 'Completed'" label="Reopen" icon-left="rotate-ccw" :loading="busy" @click="reopen" />
		</PageHeader>

		<div v-if="!review" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-4xl space-y-4 p-4 pb-28 lg:p-6 lg:pb-28">
			<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
				<p v-for="e in errors" :key="e">{{ e }}</p>
			</div>

			<section class="rounded-lg border bg-white px-4 py-3 text-sm text-gray-700">
				<p v-if="review.intro" class="mb-2">{{ review.intro }}</p>
				<p><b>{{ review.employee_name }}</b> with <b>{{ review.manager_name || "their manager" }}</b> ·
					{{ date(review.period_start) }} – {{ date(review.period_end) }} · due {{ date(review.due_on) }}</p>
				<p class="mt-1 text-gray-500">{{ guidance }}</p>
				<p v-if="review.appraisal" class="mt-2 text-gray-600">Counted in appraisal
					<a :href="deskUrl('Appraisal', review.appraisal)" target="_blank" class="text-blue-700 hover:underline">{{ review.appraisal }} ↗</a></p>
				<p v-else-if="review.rollup_note" class="mt-2 text-gray-500">{{ review.rollup_note }}</p>
			</section>

			<section class="divide-y rounded-lg border bg-white">
				<div v-for="a in shownAnswers" :key="a.name" class="space-y-3 px-4 py-4">
					<div>
						<div class="font-medium">{{ a.question }}<span v-if="a.required" class="text-red-500"> *</span></div>
						<div v-if="a.help" class="text-xs text-gray-500">{{ a.help }}</div>
					</div>
					<div v-if="a.answered_by !== 'Manager'" class="grid gap-1 sm:grid-cols-[110px_1fr] sm:items-start">
						<div class="text-xs font-medium uppercase tracking-wide text-gray-400 sm:pt-2">{{ who.employee }}</div>
						<ReviewAnswer v-model="draft[a.name].employee" :kind="a.kind" :options="a.options" :readonly="!review.can_edit_self" />
					</div>
					<div v-if="a.answered_by !== 'Employee' && showManager" class="grid gap-1 sm:grid-cols-[110px_1fr] sm:items-start">
						<div class="text-xs font-medium uppercase tracking-wide text-gray-400 sm:pt-2">{{ who.manager }}</div>
						<ReviewAnswer v-model="draft[a.name].manager" :kind="a.kind" :options="a.options" :readonly="!review.can_edit_manager" />
					</div>
				</div>
				<div v-if="showManager" class="space-y-1 px-4 py-4">
					<div class="font-medium">Manager's comments</div>
					<textarea v-if="review.can_edit_manager" v-model="comments" rows="3" class="form-textarea w-full" />
					<p v-else class="whitespace-pre-line text-sm" :class="review.manager_comments ? '' : 'text-gray-400'">{{ review.manager_comments || "—" }}</p>
				</div>
			</section>
		</div>

		<div v-if="editable" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-4xl flex-wrap items-center gap-3">
				<p class="min-w-0 flex-1 text-sm text-gray-600">{{ review.can_edit_self ? "Sending passes it to your manager; you can't change it after that." : "Completing shares it with the employee and adds your ratings to their appraisal." }}</p>
				<Button label="Save draft" :loading="busy === 'save'" @click="save(0)" />
				<Button variant="solid" :label="review.can_edit_self ? 'Send to my manager' : 'Complete review'" :loading="busy === 'done'" @click="save(1)" />
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import { boot } from "@/boot"
import { date } from "@/utils/format"
import { deskUrl, errorMessages, ok } from "../api"
import PageHeader from "../components/PageHeader.vue"
import ReviewAnswer from "../components/ReviewAnswer.vue"

const props = defineProps({ name: String })
const M = "erp_overrides.api.reviews"
const review = ref(null)
const draft = reactive({})
const comments = ref("")
const errors = ref([])
const busy = ref(null)

function fill(r) {
	review.value = r
	for (const a of r.answers) draft[a.name] = { employee: a.employee_answer || "", manager: a.manager_answer || "" }
	comments.value = r.manager_comments || ""
}
async function load() {
	errors.value = []
	try {
		fill(await call(`${M}.get_review`, { name: props.name }))
	} catch (e) {
		errors.value = errorMessages(e)
		review.value = { answers: [], role: null }
	}
}
watch(() => props.name, load, { immediate: true })

// the manager's questions stay out of the employee's view until the review is completed
const shownAnswers = computed(() => (review.value?.answers || []).filter((a) => a.answered_by !== "Manager" || showManager.value))
const editable = computed(() => review.value?.can_edit_self || review.value?.can_edit_manager)
const showManager = computed(() => review.value && review.value.role !== "employee" || review.value?.status === "Completed")
const who = computed(() => ({
	employee: review.value?.role === "employee" ? "You" : (review.value?.employee_name || "").split(" ")[0],
	manager: review.value?.role === "manager" ? "You" : (review.value?.manager_name || "Manager").split(" ")[0],
}))
const subtitle = computed(() => review.value?.name ? `${review.value.name} · ${review.value.schedule || ""}` : "")
const statusLabel = computed(() => {
	const r = review.value
	if (!r?.status) return ""
	const base = { Open: "Waiting for the employee", "Self done": "Waiting for the manager", Completed: "Completed" }[r.status]
	return r.overdue && r.status !== "Completed" ? `${base} · overdue` : base
})
const statusTheme = computed(() => review.value?.status === "Completed" ? "bg-green-50 text-green-800"
	: review.value?.overdue ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-900")
const guidance = computed(() => {
	const r = review.value
	if (r.can_edit_self) return "Fill in your part and send it; your manager then adds their ratings and comments."
	if (r.can_edit_manager) return r.status === "Open"
		? "The employee hasn't sent their part and the due date has passed: you can complete the review without it."
		: "Add your ratings and comments, then complete the review."
	if (r.role === "manager" && r.status === "Open") return "Waiting for the employee's part. You can add yours once they send it, or after the due date."
	if (r.role === "employee" && r.status === "Self done") return "Sent. Your manager's ratings and comments show here once they complete the review."
	return r.status === "Completed" ? `Completed ${date(r.completed_on)}.` : ""
})

async function save(done) {
	busy.value = done ? "done" : "save"
	errors.value = []
	const field = review.value.can_edit_self ? "employee" : "manager"
	const answers = Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, v[field]]))
	try {
		fill(await call(`${M}.save_review`, { name: props.name, answers, done,
			manager_comments: review.value.can_edit_manager ? comments.value : undefined }))
		ok(done ? (field === "employee" ? "Sent to your manager" : "Review completed") : "Saved")
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = null
	}
}

async function reopen() {
	busy.value = true
	try {
		fill(await call(`${M}.reopen`, { name: props.name }))
		ok("Reopened")
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		busy.value = null
	}
}
</script>
