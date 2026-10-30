<template>
	<div class="flex h-full flex-col">
		<PageHeader title="Bank" subtitle="Every statement line gets matched, created, transferred or discussed">
			<Button class="hidden sm:inline-flex" icon-left="zap" label="Rules" @click="$router.push('/bank/rules')" />
			<Button v-if="bank && !bank.opening" icon-left="flag" label="Set opening balance" @click="startOpening" />
			<Button icon-left="upload" label="Upload statement" @click="$router.push({ path: '/bank/upload', query: { account: current } })" />
		</PageHeader>

		<Dialog v-model="opening.open" :options="{ title: `Opening balance · ${bank?.account_name || bank?.name || ''}`, size: 'md' }">
			<template #body-content>
				<div class="space-y-3">
					<div class="grid grid-cols-2 gap-3">
						<label><span class="mb-1.5 block text-sm text-gray-600">As on</span><input v-model="opening.date" type="date" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Balance ({{ bank?.currency }})</span>
							<input v-model.number="opening.amount" type="number" step="0.01" class="form-input w-full text-right tabular" /></label>
					</div>
					<p class="text-xs text-gray-500">The closing balance on the statement for the day before go-live; negative if overdrawn. It's posted against
						Temporary Opening – {{ bank?.currency }}, which clears once opening debtors and creditors are in.</p>
				</div>
			</template>
			<template #actions>
				<Button class="w-full" variant="solid" label="Post opening balance" :loading="opening.busy" :disabled="!opening.amount || !opening.date" @click="postOpening" />
			</template>
		</Dialog>

		<!-- Bank accounts -->
		<div class="flex shrink-0 gap-3 overflow-x-auto border-b bg-white px-4 py-3 lg:px-6 hide-scrollbar">
			<div v-if="!banks" class="py-4"><LoadingIndicator class="h-5 w-5 text-gray-500" /></div>
			<button v-for="b in banks || []" :key="b.name" class="w-60 shrink-0 rounded-lg border p-3 text-left transition-colors"
				:class="b.name === current ? 'border-gray-900 ring-1 ring-gray-900' : 'hover:border-gray-400'" @click="pick(b.name)">
				<div class="flex items-center justify-between gap-2">
					<span class="truncate font-medium">{{ b.account_name || b.name }}</span>
					<span class="rounded bg-gray-100 px-1.5 text-xs text-gray-600">{{ b.currency }}</span>
				</div>
				<div class="mt-1 text-xs text-gray-500">In the books</div>
				<div class="font-semibold tabular">{{ cur(b.balance, b.currency) }}</div>
				<div v-if="b.statement_date" class="text-xs text-gray-500">Statement {{ cur(b.statement_balance, b.currency) }} · {{ date(b.statement_date) }}</div>
				<div class="mt-1.5 flex items-center gap-2 text-xs">
					<span :class="b.to_reconcile ? 'font-medium text-amber-700' : 'text-green-700'">
						{{ b.to_reconcile ? `${b.to_reconcile} to reconcile` : "All reconciled" }}
					</span>
					<span v-if="b.rule_hits" class="flex items-center gap-0.5 text-blue-700"><FeatherIcon name="zap" class="h-3 w-3" />{{ b.rule_hits }}</span>
				</div>
			</button>
		</div>

		<div class="flex min-h-0 flex-1">
			<!-- Statement lines -->
			<section class="flex min-w-0 flex-col border-r bg-white lg:w-[440px] lg:shrink-0" :class="selected ? 'hidden lg:flex' : 'flex w-full'">
				<div class="space-y-2 border-b p-3">
					<Chips v-model="view" :options="[{ value: 'to_reconcile', label: 'To reconcile', count: bank?.to_reconcile }, { value: 'reconciled', label: 'Reconciled' }]" />
					<div class="flex gap-2">
						<input v-model="search" type="search" class="form-input min-w-0 flex-1" placeholder="Search description, reference or amount" />
						<select v-model="direction" class="form-select w-24" aria-label="Direction">
							<option value="">All</option><option value="in">In</option><option value="out">Out</option>
						</select>
					</div>
					<div v-if="view === 'to_reconcile'" class="flex items-center justify-between gap-2">
						<label class="flex items-center gap-2 text-sm text-gray-700">
							<input v-model="ruleOnly" type="checkbox" class="form-checkbox" /> Rule matches only
						</label>
						<Button v-if="ruleOnly && rows.length" size="sm" variant="solid" :loading="bulkBusy"
							:label="progress ? `Reconciling ${progress.done} of ${progress.of}` : `OK ${picked.size || total}`" @click="okAll" />
					</div>
				</div>
				<div ref="listEl" class="min-h-0 flex-1 overflow-y-auto">
					<div v-if="loading && !rows.length" class="p-8 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
					<Empty v-else-if="!rows.length" icon="check-circle">
						{{ view === "reconciled" ? "Nothing reconciled yet." : search || ruleOnly || direction ? "No lines match." : "Nothing to reconcile. Upload the next statement." }}
					</Empty>
					<button v-for="r in rows" :key="r.name" :data-line="r.name" class="flex w-full items-start gap-3 border-b px-3 py-2.5 text-left"
						:class="r.name === selected ? 'bg-blue-50' : 'hover:bg-gray-50'" @click="open(r.name)">
						<input v-if="ruleOnly" type="checkbox" class="form-checkbox mt-1" :checked="picked.has(r.name)" @click.stop="togglePick(r.name)" />
						<div class="w-12 shrink-0 text-xs text-gray-500">{{ shortDate(r.date) }}</div>
						<div class="min-w-0 flex-1">
							<div class="line-clamp-2 text-sm">{{ r.description || r.reference_number || "—" }}</div>
							<div class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-gray-500">
								<span v-if="r.rule" class="flex items-center gap-0.5 text-blue-700"><FeatherIcon name="zap" class="h-3 w-3" />{{ r.matched_transaction_rule }}</span>
								<span v-if="r.party">{{ r.party }}</span>
								<span v-if="r.comments" class="flex items-center gap-0.5"><FeatherIcon name="message-circle" class="h-3 w-3" />{{ r.comments }}</span>
								<span v-if="r.assigned.length" class="text-amber-700">with {{ r.assigned.map(firstName).join(", ") }}</span>
							</div>
						</div>
						<div class="shrink-0 text-right text-sm font-medium tabular" :class="r.deposit ? 'text-green-700' : 'text-gray-900'">
							{{ r.deposit ? "+" : "−" }}{{ num(r.deposit || r.withdrawal) }}
						</div>
					</button>
					<div v-if="rows.length < total" class="p-3 text-center">
						<Button label="Load more" :loading="loading" @click="load(true)" />
					</div>
				</div>
			</section>

			<!-- The selected line -->
			<section class="min-w-0 flex-1 overflow-y-auto" :class="selected ? 'block' : 'hidden lg:block'">
				<LinePanel v-if="selected" :key="selected" :name="selected" :banks="banks || []" @close="selected = null" @done="afterDone" />
				<Empty v-else icon="mouse-pointer">
					Pick a line. <span class="hidden lg:inline">Keys: <kbd>j</kbd>/<kbd>k</kbd> move, <kbd>Enter</kbd> accepts the suggestion.</span>
				</Empty>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Dialog, LoadingIndicator, debounce } from "frappe-ui"
import { date } from "@/utils/format"
import { acc, cur, ok, fail } from "../api"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import Empty from "@/hr/components/Empty.vue"
import LinePanel from "../components/LinePanel.vue"

const props = defineProps({ account: String })
const router = useRouter()
const route = useRoute()

const banks = ref(null)
const current = computed(() => props.account || banks.value?.find((b) => b.to_reconcile)?.name || banks.value?.[0]?.name)
const bank = computed(() => banks.value?.find((b) => b.name === current.value))
const view = ref("to_reconcile")
const search = ref("")
const direction = ref("")
const ruleOnly = ref(false)
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const selected = ref(null)
const picked = ref(new Set())
const bulkBusy = ref(false)
const progress = ref(null)
const listEl = ref(null)

const num = (v) => Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const shortDate = (d) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })
const opening = ref({ open: false, date: "", amount: null, busy: false })
function startOpening() {
	opening.value = { open: true, date: "", amount: null, busy: false }
}
async function postOpening() {
	opening.value.busy = true
	try {
		const name = await acc("set_opening_balance", { bank_account: current.value, date: opening.value.date, amount: opening.value.amount })
		ok("Opening balance posted", name)
		opening.value.open = false
		await loadBanks()
	} catch (e) {
		fail(e)
	} finally {
		opening.value.busy = false
	}
}
const firstName = (u) => String(u).split("@")[0].split(".")[0]

function pick(name) {
	router.push(`/bank/${encodeURIComponent(name)}`)
}

async function loadBanks() {
	try {
		banks.value = await acc("get_banks")
	} catch (e) {
		fail(e, "Could not load the bank accounts")
	}
}

async function load(more = false) {
	if (!current.value) return
	loading.value = true
	try {
		const out = await acc("get_lines", {
			bank_account: current.value, view: view.value, search: search.value || undefined, rule_only: ruleOnly.value ? 1 : 0,
			direction: direction.value || undefined, start: more ? rows.value.length : 0, page_length: 50,
		})
		rows.value = more ? rows.value.concat(out.rows) : out.rows
		total.value = out.total
	} catch (e) {
		fail(e, "Could not load the statement lines")
	} finally {
		loading.value = false
	}
}

function open(name) {
	selected.value = name
}

function togglePick(name) {
	const s = new Set(picked.value)
	s.has(name) ? s.delete(name) : s.add(name)
	picked.value = s
}

// After a line is dealt with: drop it and move to the next one, like Xero
function afterDone(name) {
	const i = rows.value.findIndex((r) => r.name === name)
	if (view.value === "to_reconcile" && i >= 0) {
		rows.value.splice(i, 1)
		total.value -= 1
		selected.value = rows.value[Math.min(i, rows.value.length - 1)]?.name || null
	} else {
		load()
	}
	loadBanks()
}

// Ticked lines, or every rule match under the current filters (not just the loaded page).
// Posted in batches so a few hundred lines don't run into the request timeout.
async function okAll() {
	bulkBusy.value = true
	const done = [], failed = []
	try {
		const names = picked.value.size
			? [...picked.value]
			: await acc("get_rule_line_names", { bank_account: current.value, search: search.value || undefined, direction: direction.value || undefined })
		progress.value = { done: 0, of: names.length }
		for (let i = 0; i < names.length; i += 25) {
			const out = await acc("apply_rule", { names: names.slice(i, i + 25) })
			done.push(...out.done)
			failed.push(...out.failed)
			progress.value = { done: i + out.done.length + out.failed.length, of: names.length }
		}
		ok(`Reconciled ${done.length}`, failed.length ? `${failed.length} need a look: ${failed[0].error}` : "Posted by their rules")
		picked.value = new Set()
		selected.value = null
		await Promise.all([load(), loadBanks()])
	} catch (e) {
		// a batch failed outright; say how far it got
		if (done.length) ok(`Reconciled ${done.length}`, "Then stopped. Run OK again for the rest.")
		fail(e)
		await Promise.all([load(), loadBanks()])
	} finally {
		bulkBusy.value = false
		progress.value = null
	}
}

// j / k move through the list; Enter is handled by the panel
function onKey(e) {
	if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || e.metaKey || e.ctrlKey) return
	if (e.key !== "j" && e.key !== "k") return
	const i = rows.value.findIndex((r) => r.name === selected.value)
	const next = rows.value[e.key === "j" ? i + 1 : Math.max(i - 1, 0)]
	if (next) {
		selected.value = next.name
		listEl.value?.querySelector(`[data-line="${CSS.escape(next.name)}"]`)?.scrollIntoView({ block: "nearest" })
	}
}
onMounted(() => window.addEventListener("keydown", onKey))
onBeforeUnmount(() => window.removeEventListener("keydown", onKey))

const reload = debounce(() => load(), 300)
watch([view, direction, ruleOnly], () => {
	selected.value = null
	picked.value = new Set()
	load()
})
watch(search, reload)
watch(current, (v, old) => {
	if (v && v !== old) {
		selected.value = null
		load()
	}
})

loadBanks().then(() => {
	load()
	if (route.query.line) selected.value = route.query.line // from Home: a line someone asked about
})
</script>
