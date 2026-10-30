<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Settings" subtitle="Default price lists and item settings; every change is recorded" />
		<SettingsPage ref="page" app="sysadmin" :hide-sections="[SECTION]">
			<template #before>
				<!-- The default selling price list, with what each list holds -->
				<section class="rounded-lg border bg-white">
					<header class="border-b px-4 py-3">
						<h3 class="font-semibold">Default selling price list</h3>
						<p class="text-xs text-gray-500">Selling Settings → Default Price List. Used for new quotations, sales orders and invoices when the customer has no price list of their own.</p>
					</header>
					<div v-if="!current" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<div v-else class="space-y-4 p-4">
						<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
							<Facts :facts="current" label="Now" />
							<Facts v-if="next" :facts="next" label="Changing to" highlight />
							<label v-else class="block">
								<span class="mb-1.5 block text-sm text-gray-600">Change to</span>
								<select v-model="choice" class="form-select w-full" aria-label="New default selling price list">
									<option value="">Pick a price list…</option>
									<option v-for="l in choices" :key="l.name" :value="l.name">{{ l.name }} ({{ l.currency }}, {{ l.prices }} prices)</option>
								</select>
							</label>
						</div>
						<div v-if="next" class="flex flex-wrap items-center gap-2">
							<p class="min-w-0 flex-1 text-sm">
								<b>{{ current.name }}</b> → <b class="text-blue-800">{{ next.name }}</b>.
								<span v-if="next.currency !== current.currency" class="text-amber-800">New documents will default to {{ next.currency }} instead of {{ current.currency }}.</span>
								<span v-if="next.sales_items_without_price > current.sales_items_without_price" class="text-amber-800">
									{{ next.sales_items_without_price - current.sales_items_without_price }} more sales items will have no price.</span>
							</p>
							<Button label="Cancel" @click="choice = ''" />
							<Button variant="solid" label="Make it the default" :loading="saving" @click="save" />
						</div>
					</div>
				</section>
			</template>
		</SettingsPage>
	</div>
</template>

<script setup>
import { computed, h, ref, watch } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import SettingsPage from "@/components/SettingsPage.vue"
import { boot } from "@/boot"
import { relative } from "@/utils/format"
import { adm, fail, ok } from "../api"

const SECTION = "Default selling price list"
const page = ref(null)
const lists = ref([])
const current = ref(null)
const next = ref(null)
const choice = ref("")
const saving = ref(false)

const choices = computed(() => lists.value.filter((l) => l.enabled && l.selling && l.name !== current.value?.name))

async function load() {
	try {
		const res = await adm("get_price_lists")
		lists.value = res.lists
		current.value = res.selling_default ? await adm("price_list_facts", { price_list: res.selling_default }) : { name: "None set" }
	} catch (e) {
		fail(e, "Could not load price lists")
	}
}
load()

watch(choice, async (v) => {
	next.value = v ? await adm("price_list_facts", { price_list: v }).catch((e) => fail(e)) : null
})

async function save() {
	saving.value = true
	try {
		await call("erp_overrides.api.app_settings.save_settings", {
			app: "sysadmin", changes: [{ doctype: "Selling Settings", fieldname: "selling_price_list", value: next.value.name }],
		})
		ok("Default selling price list changed", `${current.value.name} → ${next.value.name}`)
		boot.selling_price_list = next.value.name
		choice.value = ""
		await load()
		page.value?.reload()
	} catch (e) {
		fail(e, "Not changed")
	} finally {
		saving.value = false
	}
}

const Facts = (p) => {
	const f = p.facts
	return h("div", { class: ["rounded border p-3 text-sm", p.highlight ? "border-blue-300 bg-blue-50" : ""] }, [
		h("div", { class: "text-xs uppercase tracking-wide text-gray-500" }, p.label),
		h("div", { class: "mt-0.5 text-lg font-semibold" }, f.name),
		f.currency ? h("dl", { class: "mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-gray-700" }, [
			h("dt", { class: "text-gray-500" }, "Currency"), h("dd", f.currency),
			h("dt", { class: "text-gray-500" }, "Item prices"), h("dd", { class: "tabular" }, f.prices),
			h("dt", { class: "text-gray-500" }, "Sales items with no price"), h("dd", { class: "tabular" }, `${f.sales_items_without_price} of ${f.sales_items}`),
			h("dt", { class: "text-gray-500" }, "Last price change"), h("dd", f.last_changed ? relative(f.last_changed) : "—"),
			!f.enabled ? h("dd", { class: "col-span-2 text-red-700" }, "Disabled") : null,
		]) : null,
	])
}
Facts.props = ["facts", "label", "highlight"]
</script>
