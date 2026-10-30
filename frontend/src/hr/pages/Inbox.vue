<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Inbox" subtitle="Approve or reject — nothing reaches a balance or a payment until you do">
			<Button icon="refresh-cw" label="Refresh" variant="ghost" :loading="loading" @click="load" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6 space-y-4">
			<Chips v-model="kind" :options="kinds" />

			<div v-if="loading && !loaded" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<Empty v-else-if="!visible.length" icon="check-circle">Nothing waiting for you.</Empty>

			<div class="grid grid-cols-1 gap-4 xl:grid-cols-2 min-[1800px]:grid-cols-3 items-start">
				<!-- Leave -->
				<article v-for="r in show('leave') ? leave : []" :key="r.name" class="rounded-lg border bg-white">
					<header class="flex items-start justify-between gap-3 border-b px-4 py-3">
						<div class="min-w-0">
							<div class="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
								<FeatherIcon name="calendar" class="h-3.5 w-3.5" /> Leave · {{ r.name }}
							</div>
							<div class="truncate font-semibold">{{ r.employee_name }}</div>
							<div class="text-sm text-gray-500">{{ r.department || "No department" }}</div>
						</div>
						<div class="text-right">
							<div class="text-lg font-semibold tabular">{{ fmtDays(r.total_leave_days) }}</div>
							<div class="text-sm text-gray-500">{{ r.leave_type }}</div>
						</div>
					</header>
					<div class="space-y-3 px-4 py-3 text-sm">
						<div class="flex flex-wrap gap-x-6 gap-y-1">
							<div><span class="text-gray-500">From</span> {{ date(r.from_date) }}</div>
							<div><span class="text-gray-500">To</span> {{ date(r.to_date) }}<span v-if="r.half_day" class="text-gray-500"> (half day)</span></div>
						</div>
						<p v-if="r.is_lwp" class="rounded bg-gray-50 px-3 py-2 text-gray-600">
							Unpaid leave — no balance is used; payroll deducts these days.
						</p>
						<div v-else class="grid grid-cols-2 gap-2">
							<div class="rounded bg-gray-50 px-3 py-2">
								<div class="text-xs text-gray-500">Balance before</div>
								<div class="font-medium tabular">{{ fmtDays(r.leave_balance) }}</div>
							</div>
							<div class="rounded px-3 py-2" :class="r.balance_after < 0 ? 'bg-red-50 text-red-800' : 'bg-gray-50'">
								<div class="text-xs" :class="r.balance_after < 0 ? 'text-red-700' : 'text-gray-500'">After approval</div>
								<div class="font-medium tabular">{{ fmtDays(r.balance_after) }}</div>
							</div>
						</div>
						<p v-if="!r.is_lwp && !Number(r.leave_balance)" class="text-xs text-amber-700">
							A balance of 0 usually means there is no allocation for this type, not that they used it all.
						</p>
						<p v-if="r.description" class="whitespace-pre-line text-gray-700">“{{ r.description }}”</p>
						<div v-if="r.overlaps.length" class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
							<div class="text-xs font-medium uppercase tracking-wide">Also away from {{ r.department }}</div>
							<div v-for="o in r.overlaps" :key="o.employee_name + o.from_date">
								{{ o.employee_name }} · {{ date(o.from_date) }} – {{ date(o.to_date) }} <span class="text-amber-700">({{ o.status }})</span>
							</div>
						</div>
					</div>
					<Decision :busy="busy[r.name]" @decide="(s, c) => decideLeave(r, s, c)" />
				</article>

				<!-- Expense claims -->
				<article v-for="r in show('expense') ? claims : []" :key="r.name" class="rounded-lg border bg-white">
					<header class="flex items-start justify-between gap-3 border-b px-4 py-3">
						<div class="min-w-0">
							<div class="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
								<FeatherIcon name="credit-card" class="h-3.5 w-3.5" /> Expense claim · {{ r.name }}
							</div>
							<div class="truncate font-semibold">{{ r.employee_name }}</div>
							<div class="text-sm text-gray-500">{{ date(r.posting_date) }}</div>
						</div>
						<div class="text-right">
							<div class="text-lg font-semibold tabular">{{ money(sanctionTotal(r), r.currency) }}</div>
							<div v-if="sanctionTotal(r) !== r.total_claimed_amount" class="text-sm text-gray-500 line-through tabular">
								{{ money(r.total_claimed_amount, r.currency) }}
							</div>
							<div v-else class="text-sm text-gray-500">claimed</div>
						</div>
					</header>
					<table class="w-full table-fixed text-sm tabular">
						<thead>
							<tr class="text-left text-xs uppercase tracking-wide text-gray-500">
								<th class="px-4 py-2 font-medium">Expense</th>
								<th class="w-28 px-2 py-2 text-right font-medium">Claimed</th>
								<th class="w-32 px-4 py-2 text-right font-medium">Sanctioned</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="e in r.expenses" :key="e.name" class="border-t align-top">
								<td class="px-4 py-2">
									<div class="font-medium">{{ e.expense_type }}</div>
									<div class="text-xs text-gray-500">{{ date(e.expense_date) }}</div>
									<div v-if="e.description" class="text-xs text-gray-500 line-clamp-2">{{ strip(e.description) }}</div>
								</td>
								<td class="px-2 py-2 text-right">{{ money(e.amount, r.currency) }}</td>
								<td class="px-4 py-1.5">
									<input v-model.number="sanction[r.name][e.name]" type="number" step="any" min="0" :max="e.amount"
										class="form-input w-full text-right tabular" :aria-label="`Sanctioned for ${e.expense_type}`" />
								</td>
							</tr>
						</tbody>
					</table>
					<div class="border-t px-4 py-3">
						<div class="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Receipts</div>
						<div v-if="r.attachments.length" class="flex flex-wrap gap-2">
							<a v-for="f in r.attachments" :key="f.file_url" :href="f.file_url" target="_blank"
								class="flex items-center gap-1.5 rounded border px-2 py-1 text-sm text-gray-700 hover:bg-gray-50">
								<img v-if="isImage(f.file_url)" :src="f.file_url" class="h-8 w-8 rounded object-cover" alt="" />
								<FeatherIcon v-else name="paperclip" class="h-4 w-4" />
								<span class="max-w-[12rem] truncate">{{ f.file_name }}</span>
							</a>
						</div>
						<p v-else class="text-sm text-amber-700">No receipt attached.</p>
						<p class="mt-2 text-xs text-gray-500">You can reduce a line; the difference stays visible on the claim.</p>
					</div>
					<Decision :busy="busy[r.name]" @decide="(s, c) => decideExpense(r, s, c)" />
				</article>

				<!-- Attendance requests -->
				<article v-for="r in show('attendance') ? attendance : []" :key="r.name" class="rounded-lg border bg-white">
					<header class="border-b px-4 py-3">
						<div class="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
							<FeatherIcon name="check-square" class="h-3.5 w-3.5" /> Attendance request · {{ r.name }}
						</div>
						<div class="truncate font-semibold">{{ r.employee_name }}</div>
						<div class="text-sm text-gray-500">{{ r.reason }} · {{ date(r.from_date) }}<template v-if="r.to_date !== r.from_date"> – {{ date(r.to_date) }}</template></div>
					</header>
					<div class="px-4 py-3 text-sm space-y-1">
						<p v-if="r.explanation" class="whitespace-pre-line text-gray-700">“{{ r.explanation }}”</p>
						<p v-if="r.half_day" class="text-gray-500">Half day on {{ date(r.half_day_date) }}</p>
						<p v-if="r.include_holidays" class="text-gray-500">Includes holidays</p>
						<p class="text-xs text-gray-500">Approving marks the attendance for these days. Declining sends it back to them with your reason.</p>
					</div>
					<Decision :busy="busy[r.name]" approve-label="Approve" reject-label="Decline" reject-needs-comment
						@decide="(s, c) => decideAttendance(r, s, c)" />
				</article>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref } from "vue"
import { LoadingIndicator } from "frappe-ui"
import { money, date } from "@/utils/format"
import { hr, ok, fail } from "../api"
import { setInboxCount } from "../data/inbox"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import Empty from "../components/Empty.vue"
import Decision from "../components/Decision.vue"

const kind = ref("all")
const leave = ref([])
const claims = ref([])
const attendance = ref([])
const sanction = reactive({})
const busy = reactive({})
const loading = ref(false)
const loaded = ref(false)

const kinds = computed(() => [
	{ value: "all", label: "All", count: leave.value.length + claims.value.length + attendance.value.length },
	{ value: "leave", label: "Leave", count: leave.value.length },
	{ value: "expense", label: "Claims", count: claims.value.length },
	{ value: "attendance", label: "Attendance", count: attendance.value.length },
])
const show = (k) => kind.value === "all" || kind.value === k
const visible = computed(() => [
	...(show("leave") ? leave.value : []), ...(show("expense") ? claims.value : []), ...(show("attendance") ? attendance.value : []),
])

const fmtDays = (n) => `${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })} day${Number(n) === 1 ? "" : "s"}`
const strip = (s) => String(s || "").replace(/<[^>]+>/g, " ").trim()
const isImage = (url) => /\.(png|jpe?g|gif|webp|heic)$/i.test(url || "")
const sanctionTotal = (r) => r.expenses.reduce((s, e) => s + Number(sanction[r.name]?.[e.name] ?? e.amount ?? 0), 0)

async function load() {
	loading.value = true
	try {
		const [l, c, a] = await Promise.all([hr("get_leave_inbox"), hr("get_expense_inbox"), hr("get_attendance_inbox")])
		leave.value = l
		claims.value = c
		attendance.value = a
		for (const r of c) {
			sanction[r.name] = Object.fromEntries(r.expenses.map((e) => [e.name, Number(e.sanctioned_amount) || Number(e.amount)]))
		}
		setInboxCount({ leave: l.length, expense: c.length, attendance: a.length })
	} catch (e) {
		fail(e, "Could not load the inbox")
	} finally {
		loading.value = false
		loaded.value = true
	}
}

async function decide(r, list, call, doneText) {
	busy[r.name] = true
	try {
		await call()
		list.value = list.value.filter((x) => x.name !== r.name)
		setInboxCount({ leave: leave.value.length, expense: claims.value.length, attendance: attendance.value.length })
		ok(doneText, `${r.employee_name} · ${r.name}`)
	} catch (e) {
		fail(e)
	} finally {
		busy[r.name] = false
	}
}

const decideLeave = (r, status, comment) =>
	decide(r, leave, () => hr("decide_leave", { name: r.name, status, comment }), status === "Approved" ? "Leave approved" : "Leave rejected")

const decideExpense = (r, status, comment) =>
	decide(r, claims, () => hr("decide_expense", { name: r.name, status, comment, sanctioned: sanction[r.name] }),
		status === "Approved" ? "Claim approved" : "Claim rejected")

const decideAttendance = (r, status, comment) =>
	decide(r, attendance, () => hr("decide_attendance_request", { name: r.name, approve: status === "Approved" ? 1 : 0, comment }),
		status === "Approved" ? "Attendance approved" : "Sent back to the employee")

load()
</script>
