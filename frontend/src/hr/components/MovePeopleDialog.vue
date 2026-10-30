<template>
	<Dialog :model-value="open" :options="{ title: `Move people to ${to}`, size: '3xl' }" @update:model-value="(v) => !v && $emit('close')">
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-gray-700">
					{{ count }} {{ count === 1 ? "person is" : "people are" }} on <strong>{{ from }}</strong>. Their payslips from the date below use
					<strong>{{ to }}</strong>; earlier payslips stay as they were. Everyone keeps their gross.
				</p>
				<label class="block max-w-xs"><span class="mb-1.5 block text-sm text-gray-600">From</span>
					<input v-model="fromDate" type="date" class="form-input w-full" /></label>

				<div v-if="loading" class="p-6 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
				<div v-else-if="rows.length" class="overflow-x-auto rounded border">
					<table class="w-full text-sm">
						<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
							<tr><th class="px-3 py-2">Employee</th><th class="px-3 py-2 text-right">Gross</th><th class="px-3 py-2 text-right">Net now</th>
								<th class="px-3 py-2 text-right">Net after</th><th class="px-3 py-2 text-right">Change</th></tr>
						</thead>
						<tbody class="divide-y tabular">
							<tr v-for="r in rows" :key="r.employee">
								<td class="px-3 py-2">{{ r.employee_name }}</td>
								<td class="px-3 py-2 text-right">{{ m(r.base) }}</td>
								<template v-if="r.error"><td colspan="3" class="px-3 py-2 text-right text-red-700">{{ r.error }}</td></template>
								<template v-else>
									<td class="px-3 py-2 text-right">{{ m(r.net_now) }}</td>
									<td class="px-3 py-2 text-right">{{ m(r.net_new) }}</td>
									<td class="px-3 py-2 text-right" :class="diff(r) > 0 ? 'text-green-700' : diff(r) < 0 ? 'text-amber-700' : 'text-gray-400'">
										{{ diff(r) ? (diff(r) > 0 ? "+" : "−") + m(Math.abs(diff(r))) : "same" }}</td>
								</template>
							</tr>
						</tbody>
					</table>
				</div>
				<p v-else class="text-sm text-gray-500">Nobody is on {{ from }} on that date.</p>
				<p v-if="changed" class="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
					{{ changed }} {{ changed === 1 ? "person's" : "people's" }} take-home changes. If you agreed a take-home with them,
					re-gross them on <router-link to="/salaries" class="underline">Salaries</router-link> after moving.
				</p>
				<div v-if="failed.length" class="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
					<p v-for="x in failed" :key="x.employee">{{ nameOf(x.employee) }} — {{ x.error }}</p>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex flex-wrap justify-end gap-2">
				<Button label="Not now" @click="$emit('close')" />
				<Button variant="solid" :label="`Move ${count} ${count === 1 ? 'person' : 'people'}`" :disabled="!count || loading" :loading="moving" @click="confirm" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Dialog, LoadingIndicator } from "frappe-ui"
import { money } from "@/utils/format"
import { boot } from "@/boot"
import { pay, ok, fail } from "../api"

const props = defineProps({ open: Boolean, kind: String, from: String, to: String })
const emit = defineEmits(["close", "moved"])

const next = new Date()
next.setMonth(next.getMonth() + 1, 1)
const fromDate = ref(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-01`)
const rows = ref([])
const failed = ref([])
const loading = ref(false)
const moving = ref(false)

const m = (v) => money(v || 0, boot.currency)
const diff = (r) => Math.round(((r.net_new || 0) - (r.net_now || 0)) * 100) / 100
const count = computed(() => rows.value.length)
const changed = computed(() => rows.value.filter((r) => !r.error && diff(r)).length)
const nameOf = (id) => rows.value.find((r) => r.employee === id)?.employee_name || id

async function load() {
	if (!props.open || !fromDate.value) return
	loading.value = true
	failed.value = []
	try {
		rows.value = (await pay("move_people", { kind: props.kind, old: props.from, new: props.to, from_date: fromDate.value })).rows
	} catch (e) {
		fail(e, "Could not work out the move")
	} finally {
		loading.value = false
	}
}

async function confirm() {
	moving.value = true
	try {
		const out = await pay("move_people", { kind: props.kind, old: props.from, new: props.to, from_date: fromDate.value, confirm: 1 })
		failed.value = out.failed
		ok(`Moved ${out.moved} to ${props.to}`, out.failed.length ? `${out.failed.length} not moved — see the list` : "From the date you picked")
		if (!out.failed.length) emit("moved")
	} catch (e) {
		fail(e)
	} finally {
		moving.value = false
	}
}

watch(() => [props.open, fromDate.value], load, { immediate: true })
</script>
