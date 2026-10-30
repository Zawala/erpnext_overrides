<template>
	<Dialog :model-value="!!doctype" :options="{ title: `New ${doctype}`, size: 'lg' }" @update:model-value="(v) => !v && close()">
		<template #body-content>
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
				<Field v-for="f in fields" :key="f.fieldname" :field="f" :doc="doc" @change="(k, v) => (doc[k] = v)" />
			</div>
			<p v-if="doctype === 'Supplier'" class="mt-4 text-xs text-gray-500">
				Accounts cannot approve a purchase order to a supplier that does not exist. Set the billing currency now —
				changing it after the first transaction is painful.
			</p>
			<ul v-if="errors.length" class="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 space-y-1">
				<li v-for="m in errors" :key="m">{{ m }}</li>
			</ul>
		</template>
		<template #actions>
			<Button variant="solid" class="w-full" :label="`Create ${doctype}`" :loading="saving" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { Dialog, call } from "frappe-ui"
import Field from "./Field.vue"
import { boot } from "@/boot"
import { errorMessages } from "@/utils/api"

const props = defineProps({ doctype: String, initialName: String })
const emit = defineEmits(["created", "close"])

const FIELDS = {
	Customer: [
		{ fieldname: "customer_name", label: "Customer name", type: "Data", reqd: true, span: 2 },
		{ fieldname: "customer_type", label: "Type", type: "Select", options: ["Company", "Individual"] },
		{ fieldname: "customer_group", label: "Customer group", type: "Link", options: "Customer Group", filters: () => ({ is_group: 0 }) },
		{ fieldname: "territory", label: "Territory", type: "Link", options: "Territory", filters: () => ({ is_group: 0 }) },
		{ fieldname: "default_currency", label: "Billing currency", type: "Link", options: "Currency" },
		{ fieldname: "tax_id", label: "Tax ID", type: "Data" },
	],
	Supplier: [
		{ fieldname: "supplier_name", label: "Supplier name", type: "Data", reqd: true, span: 2,
			help: "Exactly as they invoice — “Example Holdings (Pvt) Ltd”, not “Example”" },
		{ fieldname: "supplier_type", label: "Type", type: "Select", options: ["Company", "Individual"] },
		{ fieldname: "supplier_group", label: "Supplier group", type: "Link", options: "Supplier Group", filters: () => ({ is_group: 0 }),
			help: "Change from Local for international vendors" },
		{ fieldname: "default_currency", label: "Billing currency", type: "Link", options: "Currency" },
		{ fieldname: "payment_terms", label: "Payment terms", type: "Link", options: "Payment Terms Template",
			help: "Their terms, not ours" },
		{ fieldname: "country", label: "Country", type: "Link", options: "Country" },
		{ fieldname: "tax_id", label: "Tax ID", type: "Data" },
	],
}

const fields = computed(() => FIELDS[props.doctype] || [])
const doc = reactive({})
const saving = ref(false)
const errors = ref([])

watch(
	() => props.doctype,
	(dt) => {
		if (!dt) return
		for (const k of Object.keys(doc)) delete doc[k]
		const nameField = dt === "Customer" ? "customer_name" : "supplier_name"
		Object.assign(doc, { doctype: dt, [nameField]: props.initialName || "", default_currency: boot.currency },
			dt === "Customer" ? { customer_type: "Company" } : { supplier_type: "Company" })
		errors.value = []
	}
)

const close = () => emit("close")

async function save() {
	saving.value = true
	errors.value = []
	try {
		const created = await call("frappe.client.insert", { doc: { ...doc } })
		emit("created", created.name)
		close()
	} catch (e) {
		errors.value = errorMessages(e)
	} finally {
		saving.value = false
	}
}
</script>
