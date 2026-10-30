<template>
	<div v-if="status?.needs_approval || approvedSomething" class="rounded-lg border p-4"
		:class="status?.needs_approval ? 'border-amber-300 bg-amber-50' : 'border-green-200 bg-green-50'">
		<div class="flex items-start gap-3">
			<FeatherIcon :name="status?.needs_approval ? 'alert-triangle' : 'check-circle'" class="mt-0.5 h-5 w-5 shrink-0"
				:class="status?.needs_approval ? 'text-amber-600' : 'text-green-600'" />
			<div class="flex-1 min-w-0">
				<p class="font-medium" :class="status?.needs_approval ? 'text-amber-900' : 'text-green-900'">
					{{ status?.needs_approval ? "This order requires Sales Master Manager approval before submission." : "Approved — you can submit this order." }}
				</p>
				<ul class="mt-2 space-y-1.5 text-sm">
					<li v-if="status.discount_breached" class="flex flex-wrap items-center gap-x-3 gap-y-1">
						<span :class="status.discount_approved ? 'text-green-800' : 'text-amber-900'">
							{{ status.discount_approved ? "✓ Discount approved" : `Discount of ${status.max_discount}% exceeds the allowed limit of ${status.limits.discount_limit}%.` }}
						</span>
						<Button v-if="status.can_approve && !status.discount_approved" size="sm" variant="solid" label="Approve discount"
							:loading="busy === 'custom_discount_approved'" @click="approve('custom_discount_approved')" />
					</li>
					<li v-if="status.credit_breached" class="flex flex-wrap items-center gap-x-3 gap-y-1">
						<span :class="status.credit_approved ? 'text-green-800' : 'text-amber-900'">
							{{ status.credit_approved ? "✓ Credit approved" : `Order value ${money(status.total)} exceeds the credit limit of ${money(status.limits.sales_order_limit)}.` }}
						</span>
						<Button v-if="status.can_approve && !status.credit_approved" size="sm" variant="solid" label="Approve credit"
							:loading="busy === 'custom_credit_approval'" @click="approve('custom_credit_approval')" />
					</li>
				</ul>
				<div v-if="status?.needs_approval && !status.can_approve" class="mt-3 flex flex-wrap items-center gap-2">
					<Button variant="solid" icon-left="send" label="Ask a manager to approve" @click="askOpen = true" />
					<span class="text-xs text-amber-800">Don't reduce the value to sneak under the limit.</span>
				</div>
				<p v-if="dirty" class="mt-2 text-xs text-amber-800">You have unsaved changes — save to re-check.</p>
			</div>
		</div>

		<Dialog v-model="askOpen" :options="{ title: 'Ask for approval', size: 'md' }">
			<template #body-content>
				<div class="space-y-4">
					<div>
						<label class="mb-1.5 block text-sm text-gray-600">Manager</label>
						<select v-model="approver" class="form-select w-full">
							<option v-for="u in approvers" :key="u.name" :value="u.name">{{ u.full_name || u.name }}</option>
						</select>
					</div>
					<div>
						<label class="mb-1.5 block text-sm text-gray-600">Note (optional)</label>
						<textarea v-model="note" rows="3" class="form-textarea w-full" placeholder="Customer signed PO attached…" />
					</div>
					<p class="text-xs text-gray-500">They get a notification with a link to this order. Once they approve, you submit.</p>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Send" :loading="sending" :disabled="!approver" @click="ask" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Dialog, FeatherIcon, call, toast } from "frappe-ui"
import { api, errorMessages } from "@/utils/api"
import { money } from "@/utils/format"
import { loadApprovals } from "@/data/approvals"

const props = defineProps({ doc: Object, dirty: Boolean })
const emit = defineEmits(["status", "approved"])

const status = ref(null)
const busy = ref(null)
const askOpen = ref(false)
const approvers = ref([])
const approver = ref("")
const note = ref("")
const sending = ref(false)

const approvedSomething = computed(
	() => status.value && (status.value.credit_breached || status.value.discount_breached) && !status.value.needs_approval
)

async function load() {
	if (!props.doc?.name || props.doc.docstatus !== 0) return (status.value = null)
	status.value = await api("get_approval_status", { sales_order: props.doc.name })
	emit("status", status.value)
}
watch(() => [props.doc?.name, props.doc?.modified, props.doc?.docstatus], load, { immediate: true })

watch(askOpen, async (open) => {
	if (open && !approvers.value.length) {
		approvers.value = await api("get_approvers")
		approver.value = approvers.value[0]?.name || ""
	}
})

async function approve(fieldname) {
	busy.value = fieldname
	try {
		await call("frappe.client.set_value", { doctype: "Sales Order", name: props.doc.name, fieldname, value: 1 })
		emit("approved")
		loadApprovals().catch(() => {})
	} catch (e) {
		toast({ title: "Approval failed", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600" })
	} finally {
		busy.value = null
	}
}

async function ask() {
	sending.value = true
	try {
		await api("request_approval", { sales_order: props.doc.name, approver: approver.value, note: note.value })
		askOpen.value = false
		toast({ title: "Sent", text: "Your manager has been notified.", icon: "check", iconClasses: "text-green-600" })
	} catch (e) {
		toast({ title: "Could not send", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600" })
	} finally {
		sending.value = false
	}
}

defineExpose({ status })
</script>
