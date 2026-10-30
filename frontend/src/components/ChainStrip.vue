<template>
	<div ref="root" class="space-y-1.5 overflow-x-auto hide-scrollbar">
		<ol v-for="lane in lanes" :key="lane.label" class="flex min-w-max items-stretch gap-1.5">
			<li class="flex w-9 shrink-0 items-center text-[11px] font-medium uppercase tracking-wide text-gray-400">{{ lane.label }}</li>
			<li v-for="(dt, i) in shown(lane)" :key="dt" class="flex items-center gap-1.5">
				<div
					class="rounded-md border px-2.5 py-1.5 min-w-[118px]"
					:data-current="stageHasCurrent(dt) && lane.label === 'Sell' ? '' : undefined"
					:class="stageHasCurrent(dt) ? 'border-gray-900 bg-white' : rows(dt).length ? 'bg-white' : 'border-dashed bg-transparent'"
				>
					<div class="text-[11px] font-medium uppercase tracking-wide" :class="rows(dt).length ? 'text-gray-500' : 'text-gray-400'">
						{{ dt }}
					</div>
					<div v-if="!rows(dt).length" class="text-sm text-gray-400">—</div>
					<router-link
						v-for="r in rows(dt)"
						:key="r.name"
						:to="docRoute(dt, r.name)"
						class="flex items-center gap-1.5 text-sm hover:underline"
						:class="r.current ? 'font-semibold text-gray-900' : 'text-gray-700'"
					>
						<span class="h-1.5 w-1.5 rounded-full shrink-0" :class="dot(r)" />
						<span class="truncate max-w-[150px]">{{ r.name }}</span>
					</router-link>
				</div>
				<FeatherIcon v-if="i < shown(lane).length - 1" name="chevron-right" class="h-3.5 w-3.5 text-gray-300 shrink-0" />
			</li>
		</ol>
	</div>
</template>

<script setup>
import { nextTick, ref, watch } from "vue"
import { FeatherIcon } from "frappe-ui"
import { chainLanes, docRoute, doctypes, optionalStages } from "@/doctypes"
import { api } from "@/utils/api"
import { statusTheme } from "@/utils/format"

const props = defineProps({ doctype: String, name: String, version: String })
const chain = ref({})
const root = ref(null)
// the Buy lane hangs off the Sales Order, so repeat it there for context
const lanes = chainLanes.map((l) => (l.label === "Buy" ? { ...l, doctypes: ["Sales Order", ...l.doctypes] } : l))
const shown = (lane) => lane.doctypes.filter((dt) => !optionalStages.includes(dt) || rows(dt).length)

const rows = (dt) => chain.value[dt] || []
const stageHasCurrent = (dt) => rows(dt).some((r) => r.current)
const dot = (r) =>
	({ green: "bg-green-500", blue: "bg-blue-500", orange: "bg-amber-500", red: "bg-red-500" })[
		statusTheme(doctypes[r.doctype].submittable && r.docstatus === 0 ? "Draft" : r.status)
	] || "bg-gray-400"

watch(
	() => [props.doctype, props.name, props.version],
	async () => {
		if (!props.name) return (chain.value = {})
		try {
			chain.value = await api("get_chain", { doctype: props.doctype, name: props.name })
			await nextTick()
			const el = root.value?.querySelector("[data-current]")
			if (el) root.value.scrollLeft = el.offsetLeft - (root.value.clientWidth - el.offsetWidth) / 2
		} catch {
			chain.value = {}
		}
	},
	{ immediate: true }
)
</script>
