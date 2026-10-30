<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="New supplier bill" subtitle="Drop the bill in, key what it says beside it — saved as a draft to check and submit" back="/payables" />

		<div class="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-4 p-4 lg:grid-cols-2 lg:p-6">
			<!-- The document -->
			<section class="rounded-lg border bg-white p-4">
				<label class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded border-2 border-dashed p-6 text-sm text-gray-500 hover:bg-gray-50"
					@dragover.prevent @drop.prevent="pick($event.dataTransfer.files[0])">
					<FeatherIcon name="upload" class="h-6 w-6" />
					<span>{{ file ? file.name : "Drop the bill here, or click to choose (PDF or photo)" }}</span>
					<input type="file" accept=".pdf,image/*" class="hidden" @change="pick($event.target.files[0])" />
				</label>
				<div v-if="previewUrl" class="mt-3 h-[60vh] overflow-hidden rounded border">
					<img v-if="isImage" :src="previewUrl" class="h-full w-full object-contain" alt="The bill" />
					<iframe v-else :src="previewUrl" class="h-full w-full" title="The bill" />
				</div>
			</section>

			<!-- What it says -->
			<section class="space-y-4 rounded-lg border bg-white p-4">
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<label class="sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Supplier <span class="text-red-500">*</span></span>
						<LinkField v-model="form.supplier" doctype="Supplier" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Bill date</span><input v-model="form.date" type="date" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Due date</span><input v-model="form.due" type="date" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">Their invoice number</span><input v-model="form.bill_no" class="form-input w-full" /></label>
					<label><span class="mb-1.5 block text-sm text-gray-600">VAT</span>
						<LinkField v-model="form.tax" doctype="Purchase Taxes and Charges Template" placeholder="No VAT" /></label>
				</div>
				<div>
					<div class="mb-1.5 text-sm text-gray-600">Lines (before VAT)</div>
					<div v-for="(l, i) in form.lines" :key="i" class="mb-2 grid grid-cols-[minmax(0,1fr)_auto] gap-2 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1.2fr)_7rem_auto]">
						<input v-model="l.description" class="form-input col-span-2 sm:col-span-1" placeholder="What for" />
						<div class="min-w-0"><LinkField v-model="l.account" doctype="Account" :filters="{ is_group: 0, root_type: 'Expense', company: boot.company }" placeholder="Expense account" /></div>
						<input v-model.number="l.amount" type="number" step="0.01" class="form-input w-full min-w-0 text-right tabular" placeholder="0.00" />
						<button class="rounded p-1.5 text-gray-500 hover:bg-gray-100" aria-label="Remove line" @click="form.lines.splice(i, 1)"><FeatherIcon name="x" class="h-4 w-4" /></button>
					</div>
					<button class="text-sm text-blue-700 hover:underline" @click="form.lines.push({ description: '', account: '', amount: null })">+ Add a line</button>
				</div>
				<div class="flex items-center justify-between border-t pt-3">
					<span class="text-sm text-gray-500">Total before VAT <b class="tabular text-gray-900">{{ cur(total) }}</b></span>
					<Button variant="solid" label="Save draft bill" :disabled="!ready" :loading="saving" @click="save" />
				</div>
				<p class="text-xs text-gray-500">The draft opens in desk to check the VAT and submit. Then it shows under We owe, and Bank suggests it when the payment comes through.</p>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { boot } from "@/boot"
import LinkField from "@/components/LinkField.vue"
import { today } from "@/utils/format"
import { acc, cur, ok, fail, deskUrl } from "../api"
import { recordRoute } from "../records"
import PageHeader from "@/hr/components/PageHeader.vue"

const router = useRouter()

const file = ref(null)
const previewUrl = ref("")
const saving = ref(false)
const form = reactive({ supplier: "", date: today(), due: "", bill_no: "", tax: "", lines: [{ description: "", account: "", amount: null }] })
const isImage = computed(() => file.value?.type?.startsWith("image/"))
const total = computed(() => form.lines.reduce((s, l) => s + Number(l.amount || 0), 0))
const ready = computed(() => form.supplier && form.lines.some((l) => l.account && Number(l.amount) > 0))

function pick(f) {
	if (!f) return
	file.value = f
	previewUrl.value = URL.createObjectURL(f)
}

async function upload() {
	if (!file.value) return undefined
	const fd = new FormData()
	fd.append("file", file.value, file.value.name)
	fd.append("is_private", "1")
	const res = await fetch("/api/method/upload_file", { method: "POST", body: fd, headers: { "X-Frappe-CSRF-Token": window.csrf_token } })
	const body = await res.json()
	if (!res.ok) throw { messages: ["Could not upload the bill"] }
	return body.message.file_url
}

async function save() {
	saving.value = true
	try {
		const name = await acc("new_supplier_bill", {
			supplier: form.supplier, posting_date: form.date, due_date: form.due || undefined, bill_no: form.bill_no || undefined,
			tax_template: form.tax || undefined, file_url: await upload(),
			lines: form.lines.filter((l) => l.account && Number(l.amount) > 0),
		})
		ok("Draft bill saved", name)
		// check the draft and submit it in the app; desk only when the role can't open it here
		const to = recordRoute("Purchase Invoice", name)
		if (to) return router.push(to)
		window.open(deskUrl("Purchase Invoice", name), "_blank")
		Object.assign(form, { supplier: "", bill_no: "", due: "", tax: "", lines: [{ description: "", account: "", amount: null }] })
		file.value = null
		previewUrl.value = ""
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}
</script>
