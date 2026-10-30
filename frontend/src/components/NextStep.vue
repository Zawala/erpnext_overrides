<template>
	<section class="rounded-lg border bg-white p-4">
		<h3 class="text-base font-semibold">Next step</h3>

		<p v-if="isDraft" class="mt-2 text-sm text-gray-600">
			Submit this {{ doc.doctype }} first — drafts produce nothing downstream.
		</p>

		<template v-else>
			<div v-for="step in steps" :key="step.target" class="mt-3">
				<Button
					:variant="step.optional ? 'subtle' : 'solid'"
					class="w-full"
					icon-right="arrow-right"
					:loading="busy === step.target"
					:disabled="step.reason !== true"
					@click="create(step.target)"
				>
					{{ step.label || `Create ${step.target}` }}
				</Button>
				<p class="mt-1 text-xs" :class="step.reason === true ? 'text-gray-500' : 'text-amber-700'">
					{{ step.reason === true ? step.hint : step.reason }}
				</p>
			</div>

			<div v-if="handOff[doc.doctype]" class="mt-2 space-y-2 text-sm text-gray-600">
				<p>{{ handOff[doc.doctype].text }}</p>
				<a :href="deskUrl" class="inline-flex items-center gap-1 font-medium text-gray-900 hover:underline">
					{{ handOff[doc.doctype].link }} <FeatherIcon name="external-link" class="h-3.5 w-3.5" />
				</a>
			</div>
			<p v-else-if="!steps.length" class="mt-2 text-sm text-gray-500">This is the end of the line.</p>
		</template>
	</section>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { FeatherIcon, toast } from "frappe-ui"
import { doctypes, nextSteps, pendingDocs, can } from "@/doctypes"
import { api, errorMessages } from "@/utils/api"

const props = defineProps({ doc: Object })
const router = useRouter()
const busy = ref(null)

const isDraft = computed(() => doctypes[props.doc.doctype].submittable && props.doc.docstatus === 0)
const steps = computed(() =>
	(nextSteps[props.doc.doctype] || [])
		.filter((s) => can(s.target, "read"))
		.map((s) => ({
			...s,
			reason: !can(s.target, "create")
				? `You can't create a ${s.target} — ask Accounts`
				: s.when ? s.when(props.doc) : true,
		}))
)

const handOff = computed(() => ({
	"Purchase Order": {
		text: "When the supplier's invoice arrives, Accounts bills it from this order in the Accounts app (We owe → Orders to bill). It's paid only once what was billed has been received.",
		link: "Open in desk",
	},
	"Purchase Receipt": {
		text: "Received. Any hardware is now in stock, and Accounts can bill and pay this much of the order.",
		link: "Open in desk",
	},
	"Sales Invoice": {
		text: props.doc.outstanding_amount > 0
			? "Accounts records the payment against this invoice, so nothing sits unallocated."
			: "Paid in full.",
		link: "Open in desk to record payment",
	},
}))
const deskUrl = computed(() => `/app/${props.doc.doctype.toLowerCase().replace(/ /g, "-")}/${props.doc.name}`)

async function create(target) {
	busy.value = target
	try {
		const mapped = await api("make_next", {
			source_doctype: props.doc.doctype,
			source_name: props.doc.name,
			target_doctype: target,
		})
		const slug = doctypes[target].slug
		pendingDocs.set(slug, mapped)
		router.push({ path: `/${slug}/new`, query: { from: `${props.doc.doctype}:${props.doc.name}` } })
	} catch (e) {
		toast({ title: `Cannot create ${target}`, text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600", timeout: 8 })
	} finally {
		busy.value = null
	}
}
</script>
