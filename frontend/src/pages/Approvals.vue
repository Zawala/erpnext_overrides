<template>
	<div class="h-full overflow-y-auto">
		<header class="flex items-center gap-3 border-b bg-white px-4 lg:px-6 h-14 sticky top-0 z-10">
			<FeatherIcon name="check-circle" class="h-5 w-5 text-gray-500" />
			<h1 class="flex-1 text-lg font-semibold">Approvals</h1>
			<Button icon="refresh-cw" :loading="loading" @click="refresh" />
		</header>

		<div class="mx-auto w-full max-w-[1400px] p-4 lg:p-6 space-y-4">
			<p class="text-sm text-gray-600">
				Draft sales orders over the {{ money(boot.limits?.sales_order_limit) }} order limit or the
				{{ boot.limits?.discount_limit }}% discount limit. You approve; the seller still submits.
			</p>

			<div v-if="!boot.is_approver" class="rounded-lg border bg-white p-6 text-gray-600">
				Only Sales Manager and Sales Master Manager can approve orders.
			</div>

			<div v-else-if="!loading && !approvals.length" class="rounded-lg border bg-white p-10 text-center text-gray-500">
				Nothing waiting. 🎉
			</div>

			<div v-else class="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
				<article v-for="a in approvals" :key="a.name" class="rounded-lg border bg-white p-4">
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<router-link :to="docRoute('Sales Order', a.name)" class="font-semibold hover:underline">{{ a.customer_name }}</router-link>
							<div class="text-sm text-gray-500">{{ a.name }} · by {{ a.owner }} · {{ relative(a.modified) }}</div>
						</div>
						<div class="text-right text-lg font-semibold tabular">{{ money(a.grand_total, a.currency) }}</div>
					</div>
					<ul class="mt-3 space-y-2 text-sm">
						<li v-if="a.credit_breached" class="flex items-center justify-between gap-3">
							<span>{{ a.credit_approved ? "✓ Credit approved" : "Over the order limit" }}</span>
							<Button v-if="!a.credit_approved" size="sm" variant="solid" label="Approve credit"
								:loading="busy === a.name + 'credit'" @click="approve(a, 'custom_credit_approval', 'credit')" />
						</li>
						<li v-if="a.discount_breached" class="flex items-center justify-between gap-3">
							<span>{{ a.discount_approved ? "✓ Discount approved" : `Line discount ${a.max_discount}%` }}</span>
							<Button v-if="!a.discount_approved" size="sm" variant="solid" label="Approve discount"
								:loading="busy === a.name + 'discount'" @click="approve(a, 'custom_discount_approved', 'discount')" />
						</li>
					</ul>
				</article>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { FeatherIcon, call, toast } from "frappe-ui"
import { boot } from "@/boot"
import { docRoute } from "@/doctypes"
import { errorMessages } from "@/utils/api"
import { money, relative } from "@/utils/format"
import { approvals, loadApprovals } from "@/data/approvals"

const loading = ref(false)
const busy = ref(null)

async function refresh() {
	loading.value = true
	try {
		await loadApprovals()
	} finally {
		loading.value = false
	}
}

async function approve(a, fieldname, key) {
	busy.value = a.name + key
	try {
		await call("frappe.client.set_value", { doctype: "Sales Order", name: a.name, fieldname, value: 1 })
		toast({ title: "Approved", text: `${a.name} — the seller can now submit it.`, icon: "check", iconClasses: "text-green-600" })
		await loadApprovals()
	} catch (e) {
		toast({ title: "Approval failed", text: errorMessages(e).join(" "), icon: "alert-circle", iconClasses: "text-red-600" })
	} finally {
		busy.value = null
	}
}

refresh()
</script>
