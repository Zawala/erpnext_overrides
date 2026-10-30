<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="isNew ? 'New review form' : form?.title || 'Review form'" subtitle="The questions of a bi-weekly review: who answers each, and which count in the appraisal" back="/reviews">
			<Button variant="solid" label="Save" :loading="saving" :disabled="!form" @click="save" />
		</PageHeader>

		<div v-if="!form" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto grid w-full max-w-[1600px] gap-4 p-4 lg:p-6 xl:grid-cols-[1fr_440px]">
			<div class="min-w-0 space-y-4">
				<div v-if="errors.length" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
					<p v-for="e in errors" :key="e">{{ e }}</p>
				</div>
				<section class="grid gap-3 rounded-lg border bg-white p-4 sm:grid-cols-[1fr_auto]">
					<label class="block"><span class="mb-1.5 block text-sm text-gray-600">Title <span class="text-red-500">*</span></span>
						<input v-model="form.title" class="form-input w-full" :disabled="!isNew" placeholder="e.g. Bi-weekly check-in" /></label>
					<label class="flex items-center gap-2 self-end pb-2 text-sm"><input v-model="form.active" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" /> Active</label>
					<label class="block sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Introduction</span>
						<textarea v-model="form.intro" rows="2" class="form-textarea w-full" placeholder="Shown at the top of every review" /></label>
				</section>

				<section class="rounded-lg border bg-white">
					<header class="flex items-center justify-between border-b px-4 py-3">
						<h2 class="font-semibold">Questions · {{ form.questions.length }}</h2>
						<Button size="sm" icon-left="plus" label="Add question" @click="add" />
					</header>
					<div v-for="(q, i) in form.questions" :key="q._key" class="grid gap-3 border-t p-4 first-of-type:border-t-0 md:grid-cols-6">
						<label class="block md:col-span-4"><span class="mb-1 block text-xs text-gray-500">Question</span>
							<input v-model="q.label" class="form-input w-full" /></label>
						<label class="block md:col-span-2"><span class="mb-1 block text-xs text-gray-500">Answer</span>
							<select v-model="q.kind" class="form-select w-full"><option v-for="k in KINDS" :key="k">{{ k }}</option></select></label>
						<label class="block md:col-span-4"><span class="mb-1 block text-xs text-gray-500">Help text</span>
							<input v-model="q.help" class="form-input w-full" placeholder="Optional" /></label>
						<label class="block md:col-span-2"><span class="mb-1 block text-xs text-gray-500">Answered by</span>
							<select v-model="q.answered_by" class="form-select w-full"><option v-for="w in WHO" :key="w">{{ w }}</option></select></label>
						<label v-if="q.kind === 'Choice'" class="block md:col-span-4"><span class="mb-1 block text-xs text-gray-500">Choices, one per line</span>
							<textarea v-model="q.options" rows="3" class="form-textarea w-full" /></label>
						<label v-if="q.kind === 'Rating' && q.answered_by !== 'Employee'" class="block md:col-span-4"><span class="mb-1 block text-xs text-gray-500">Counts in the appraisal as</span>
							<select v-model="q.criteria" class="form-select w-full"><option :value="null">— not in the appraisal —</option>
								<option v-for="c in criteria" :key="c" :value="c">{{ c }}</option></select></label>
						<div class="flex items-center gap-2 md:col-span-6">
							<label class="flex items-center gap-2 text-sm"><input v-model="q.required" type="checkbox" :true-value="1" :false-value="0" class="form-checkbox" /> Required</label>
							<span class="flex-1" />
							<Button size="sm" icon="arrow-up" aria-label="Move up" :disabled="i === 0" @click="move(i, -1)" />
							<Button size="sm" icon="arrow-down" aria-label="Move down" :disabled="i === form.questions.length - 1" @click="move(i, 1)" />
							<Button size="sm" icon="trash-2" aria-label="Remove" @click="form.questions.splice(i, 1)" />
						</div>
					</div>
					<p v-if="!form.questions.length" class="px-4 py-6 text-center text-sm text-gray-500">No questions yet.</p>
				</section>
				<p class="text-xs text-gray-500">Changes apply to reviews opened from now on; reviews already open keep their questions.</p>
			</div>

			<!-- Preview -->
			<aside class="space-y-3 xl:sticky xl:top-4 xl:self-start">
				<Chips v-model="view" :options="[{ value: 'Employee', label: 'As the employee sees it' }, { value: 'Manager', label: 'As the manager sees it' }]" />
				<section class="divide-y rounded-lg border bg-white">
					<p v-if="form.intro" class="px-4 py-3 text-sm text-gray-700">{{ form.intro }}</p>
					<div v-for="q in shown" :key="q._key" class="space-y-2 px-4 py-3">
						<div class="text-sm font-medium">{{ q.label || "Untitled question" }}<span v-if="q.required" class="text-red-500"> *</span></div>
						<div v-if="q.help" class="text-xs text-gray-500">{{ q.help }}</div>
						<ReviewAnswer v-model="sample[q._key]" :kind="q.kind" :options="q.options" />
						<div v-if="q.criteria && view === 'Manager'" class="text-xs text-gray-400">Counts in the appraisal: {{ q.criteria }}</div>
					</div>
					<p v-if="!shown.length" class="px-4 py-6 text-center text-sm text-gray-500">Nothing for the {{ view.toLowerCase() }} to answer.</p>
				</section>
			</aside>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { LoadingIndicator, call } from "frappe-ui"
import { errorMessages, ok } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import ReviewAnswer from "../components/ReviewAnswer.vue"

const KINDS = ["Rating", "Text", "Yes / No", "Choice"]
const WHO = ["Employee", "Manager", "Both"]
const props = defineProps({ name: String })
const router = useRouter()
const isNew = computed(() => props.name === "new")
const form = ref(null)
const criteria = ref([])
const errors = ref([])
const saving = ref(false)
const view = ref("Employee")
const sample = reactive({})
const key = () => Math.random().toString(36).slice(2)

call("erp_overrides.api.reviews.get_criteria").then((c) => (criteria.value = c)).catch(() => {})

async function load() {
	errors.value = []
	if (isNew.value) {
		form.value = { doctype: "Review Form", title: "", active: 1, intro: "", questions: [] }
		add()
		return
	}
	const doc = await call("frappe.client.get", { doctype: "Review Form", name: props.name })
	doc.questions.forEach((q) => (q._key = q.name))
	form.value = doc
}
watch(() => props.name, load, { immediate: true })

const shown = computed(() => form.value.questions.filter((q) => q.answered_by === view.value || q.answered_by === "Both"))

function add() {
	form.value.questions.push({ _key: key(), doctype: "Review Form Question", label: "", kind: "Text", answered_by: "Employee", required: 0 })
}
function move(i, d) {
	const qs = form.value.questions
	;[qs[i], qs[i + d]] = [qs[i + d], qs[i]]
}

async function save() {
	saving.value = true
	errors.value = []
	const doc = JSON.parse(JSON.stringify(form.value))
	doc.questions.forEach((q, i) => {
		delete q._key
		q.idx = i + 1
		if (q.kind !== "Rating" || q.answered_by === "Employee") q.criteria = null
	})
	try {
		const saved = await call(isNew.value ? "frappe.client.insert" : "frappe.client.save", { doc })
		ok("Saved", saved.name)
		if (isNew.value) router.replace(`/review-forms/${encodeURIComponent(saved.name)}`)
		else await load()
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		saving.value = false
	}
}
</script>
