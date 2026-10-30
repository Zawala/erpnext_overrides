<template>
	<section v-if="m" class="rounded-lg border bg-white p-4">
		<h3 class="text-base font-semibold">The case for accounts</h3>
		<dl class="mt-3 space-y-2 text-sm tabular">
			<div class="flex justify-between"><dt class="text-gray-500">Customer will pay us</dt><dd class="font-medium">{{ money(m.sell, m.currency) }}</dd></div>
			<div class="flex justify-between"><dt class="text-gray-500">We must pay supplier</dt>
				<dd class="font-medium">{{ m.cost ? money(m.cost, m.currency) : "—" }}</dd></div>
			<div class="flex justify-between border-t pt-2"><dt class="text-gray-700">Gross margin</dt>
				<dd class="font-semibold" :class="m.margin < 0 ? 'text-red-600' : 'text-green-700'">
					{{ m.cost ? (m.margin_pct === null ? money(m.margin, m.currency) : `${money(m.margin, m.currency)} · ${m.margin_pct}%`) : "—" }}
				</dd></div>
		</dl>
		<p v-if="m.cost && m.sell" class="mt-3 rounded bg-gray-50 p-2.5 text-sm text-gray-700">
			“Release {{ money(m.cost, m.currency) }} and a signed customer order brings back {{ money(m.sell, m.currency) }}.”
		</p>
		<p v-else-if="!m.sell" class="mt-3 text-xs text-amber-700">
			No submitted Sales Order behind this — a purchase order without one will be declined.
		</p>
		<p v-else class="mt-3 text-xs text-gray-500">No purchase order yet.</p>
		<p v-if="m.cost && m.margin_pct !== null && m.margin_pct < 10" class="mt-2 text-xs text-amber-700">
			Margin looks thin — check whether the quotation price or our cost is wrong.
		</p>
	</section>
</template>

<script setup>
import { ref, watch } from "vue"
import { api } from "@/utils/api"
import { money } from "@/utils/format"

const props = defineProps({ doctype: String, name: String, version: String })
const m = ref(null)

watch(
	() => [props.doctype, props.name, props.version],
	async () => {
		m.value = props.name ? await api("get_margin", { doctype: props.doctype, name: props.name }).catch(() => null) : null
	},
	{ immediate: true }
)
</script>
