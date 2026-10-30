<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="boot.has_reports ? 'Reviews' : 'My reviews'" subtitle="Bi-weekly check-ins: you say how it went, your manager adds ratings and comments" />
		<div class="mx-auto w-full max-w-5xl space-y-4 p-4 lg:p-6">
			<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<template v-else>
				<section v-if="waiting.length" class="rounded-lg border border-amber-200 bg-amber-50">
					<h2 class="border-b border-amber-200 px-4 py-3 font-semibold text-amber-900">Waiting on you · {{ waiting.length }}</h2>
					<ReviewRow v-for="r in waiting" :key="r.name" :r="r" :as-manager="r.manager === me" />
				</section>

				<section v-if="data.team.length" class="rounded-lg border bg-white">
					<h2 class="border-b px-4 py-3 font-semibold">Your team</h2>
					<ReviewRow v-for="r in data.team" :key="r.name" :r="r" as-manager />
				</section>

				<section class="rounded-lg border bg-white">
					<h2 class="border-b px-4 py-3 font-semibold">Your own reviews</h2>
					<Empty v-if="!data.mine.length" icon="check-square">No reviews yet. Your first one opens at the end of the period HR has set up.</Empty>
					<ReviewRow v-for="r in data.mine" :key="r.name" :r="r" />
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, h, ref } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import { RouterLink } from "vue-router"
import { boot } from "@/boot"
import { date } from "@/utils/format"
import { fail } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Empty from "../components/Empty.vue"

const data = ref(null)
const me = ref(null)
call("erp_overrides.api.reviews.my_reviews").then((d) => {
	data.value = d
	me.value = d.me
}).catch((e) => { fail(e); data.value = { mine: [], team: [] } })

const today = new Date().toISOString().slice(0, 10)
const waiting = computed(() => !data.value ? [] : [
	...data.value.mine.filter((r) => r.status === "Open"),
	...data.value.team.filter((r) => r.status === "Self done" || (r.status === "Open" && r.due_on < today)),
])

const STATUS = { Open: "Waiting for the employee", "Self done": "Waiting for the manager", Completed: "Completed" }
const ReviewRow = (props) => {
	const r = props.r
	const late = r.overdue && r.status !== "Completed"
	return h(RouterLink, { to: `/reviews/${encodeURIComponent(r.name)}`, class: "flex items-center gap-3 border-t px-4 py-3 text-sm first-of-type:border-t-0 hover:bg-gray-50" }, () => [
		h("div", { class: "min-w-0 flex-1" }, [
			h("div", { class: "truncate font-medium" }, props.asManager ? r.employee_name : `${date(r.period_start)} – ${date(r.period_end)}`),
			h("div", { class: "truncate text-xs text-gray-500" },
				props.asManager ? `${date(r.period_start)} – ${date(r.period_end)} · due ${date(r.due_on)}` : `with ${r.manager_name || "your manager"} · due ${date(r.due_on)}`),
		]),
		h("span", { class: ["shrink-0 rounded px-1.5 py-0.5 text-xs", r.status === "Completed" ? "bg-green-50 text-green-800" : late ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-900"] },
			STATUS[r.status] + (late ? " · overdue" : "")),
	])
}
ReviewRow.props = ["r", "asManager"]
</script>
