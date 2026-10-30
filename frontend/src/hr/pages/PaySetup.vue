<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Pay setup" subtitle="What a payslip is made of: components, salary structures and the PAYE bands" />

		<div v-if="!setup" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto w-full max-w-[1600px] space-y-4 p-4 lg:p-6">
			<Chips v-model="tab" :options="[
				{ value: 'structures', label: 'Salary structures', count: setup.structures.length },
				{ value: 'components', label: 'Components', count: setup.components.length },
				{ value: 'tax', label: 'Tax bands', count: setup.slabs.length },
			]" />
			<p v-if="!setup.can_edit" class="rounded bg-gray-50 px-3 py-2 text-sm text-gray-600">You can look; only an HR Manager can change pay setup.</p>

			<!-- Structures -->
			<div v-if="tab === 'structures'" class="grid grid-cols-1 items-start gap-4 lg:grid-cols-[15rem_1fr] xl:grid-cols-[15rem_1fr_22rem]">
				<nav class="space-y-1" aria-label="Salary structures">
					<button v-for="s in setup.structures" :key="s.name" class="w-full rounded-lg border px-3 py-2 text-left"
						:class="s.name === draft?.original ? 'border-gray-900 bg-white shadow-sm' : 'bg-white hover:bg-gray-50'"
						:disabled="dirty && s.name !== draft?.original" :title="dirty && s.name !== draft?.original ? 'Save or undo your changes first' : ''"
						@click="openStructure(s)">
						<div class="flex items-center justify-between gap-2">
							<span class="truncate font-medium">{{ s.name }}</span>
							<span v-if="s.is_active !== 'Yes'" class="shrink-0 rounded bg-gray-100 px-1.5 text-xs text-gray-500">Retired</span>
						</div>
						<div class="text-xs text-gray-500">{{ s.people.length ? `${s.people.length} ${s.people.length === 1 ? "person" : "people"}` : "Nobody on it" }} · {{ s.rows.length }} lines</div>
					</button>
					<Button v-if="setup.can_edit" class="w-full" icon-left="plus" label="New structure" :disabled="dirty" @click="newStructure" />
				</nav>

				<section v-if="draft" class="space-y-4 rounded-lg border bg-white p-4">
					<div class="flex flex-wrap items-end gap-3">
						<label class="min-w-[14rem] flex-1"><span class="mb-1.5 block text-sm text-gray-600">Name</span>
							<input v-model.trim="draft.name" :disabled="!setup.can_edit" class="form-input w-full" placeholder="e.g. Staff 2027" /></label>
						<template v-if="current">
							<Button v-if="setup.can_edit && current.is_active === 'Yes'" variant="ghost" label="Retire" :disabled="dirty" @click="setActive(0)" />
							<Button v-else-if="setup.can_edit" variant="ghost" label="Bring back" :disabled="dirty" @click="setActive(1)" />
						</template>
					</div>
					<p v-if="current?.people.length" class="rounded bg-blue-50 px-3 py-2 text-sm text-blue-900">
						{{ current.people.length }} {{ current.people.length === 1 ? "person is" : "people are" }} paid on this
						({{ current.people.slice(0, 4).join(", ") }}{{ current.people.length > 4 ? "…" : "" }}).
						Saving changes makes a new version, and you choose when they move to it. Past payslips don't change.
					</p>
					<StructureEditor :key="draft.original || 'new'" :rows="draft.rows" :components="setup.components" :editable="setup.can_edit"
						:currency="setup.currency" @new-component="(k) => openComponent(null, k, true)" />
				</section>

				<div v-if="draft" class="space-y-4 lg:col-start-2 xl:col-start-auto xl:sticky xl:top-20">
					<SamplePayslip :draft-structure="draftPayload" :structure-name="draft.original" :slabs="activeSlabs" :default-slab="activeSlabs[0]?.name" />
				</div>

				<footer v-if="draft && setup.can_edit" class="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 rounded-lg border bg-white px-4 py-3 shadow-sm lg:col-span-2 xl:col-span-3">
					<span class="mr-auto text-sm text-gray-500">{{ dirty ? (current?.in_use ? "Saving creates a new version; nobody moves until you say." : "Not saved yet.") : "No changes." }}</span>
					<Button label="Undo changes" :disabled="!dirty" @click="openStructure(current)" />
					<Button variant="solid" :label="current?.in_use ? 'Save as new version' : 'Save'" :disabled="!dirty || !draft.name" :loading="saving" @click="saveStructure" />
				</footer>
			</div>

			<!-- Components -->
			<section v-else-if="tab === 'components'" class="rounded-lg border bg-white">
				<header class="flex items-center justify-between border-b px-4 py-3">
					<p class="text-sm text-gray-600">The building blocks of a structure. Click one to change it.</p>
					<Button v-if="setup.can_edit" icon-left="plus" label="New component" @click="openComponent(null, 'earning')" />
				</header>
				<ul class="divide-y">
					<li v-for="c in setup.components" :key="c.name">
						<button class="grid w-full grid-cols-[1fr_auto] gap-x-4 px-4 py-3 text-left hover:bg-gray-50 sm:grid-cols-[minmax(12rem,1fr)_8rem_minmax(12rem,1.5fr)_auto]"
							:class="c.disabled ? 'opacity-60' : ''" @click="setup.can_edit && openComponent(c)">
							<span class="font-medium">{{ c.name }} <span class="ml-1 font-mono text-xs text-gray-400">{{ c.abbr }}</span></span>
							<span class="text-sm text-gray-600">{{ kindLabel(c) }}</span>
							<span class="col-span-2 text-xs text-gray-500 sm:col-span-1">{{ flags(c) }}</span>
							<span class="hidden text-xs text-gray-500 sm:block">{{ c.disabled ? "Disabled" : c.used_in.length ? `On ${c.used_in.join(", ")}` : "Not used" }}</span>
						</button>
					</li>
				</ul>
			</section>

			<!-- Tax bands -->
			<div v-else class="grid grid-cols-1 items-start gap-4 lg:grid-cols-[15rem_1fr] xl:grid-cols-[15rem_1fr_22rem]">
				<nav class="space-y-1" aria-label="Tax bands">
					<button v-for="s in setup.slabs" :key="s.name" class="w-full rounded-lg border px-3 py-2 text-left"
						:class="s.name === slab?.original ? 'border-gray-900 bg-white shadow-sm' : 'bg-white hover:bg-gray-50'"
						:disabled="slabDirty && s.name !== slab?.original" @click="openSlab(s)">
						<div class="truncate font-medium">{{ s.name }}</div>
						<div class="text-xs text-gray-500">From {{ date(s.effective_from) }} · {{ s.people.length }} {{ s.people.length === 1 ? "person" : "people" }}</div>
					</button>
					<Button v-if="setup.can_edit" class="w-full" icon-left="plus" label="New tax bands" :disabled="slabDirty" @click="newSlab" />
				</nav>

				<section v-if="slab" class="space-y-4 rounded-lg border bg-white p-4">
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_12rem]">
						<label><span class="mb-1.5 block text-sm text-gray-600">Name</span>
							<input v-model.trim="slab.name" :disabled="!setup.can_edit" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Applies from</span>
							<input v-model="slab.effective_from" type="date" :disabled="!setup.can_edit" class="form-input w-full" /></label>
					</div>
					<div>
						<h3 class="font-semibold">Monthly bands</h3>
						<p class="mb-2 text-xs text-gray-500">As ZIMRA publishes them: each band taxes the part of monthly taxable pay between its two amounts.</p>
						<table class="w-full text-sm">
							<thead class="text-left text-xs uppercase tracking-wide text-gray-500">
								<tr><th class="py-1 pr-2">From</th><th class="py-1 pr-2">Up to</th><th class="py-1 pr-2">Rate</th><th></th></tr>
							</thead>
							<tbody>
								<tr v-for="(b, i) in slab.bands" :key="i">
									<td class="py-1 pr-2"><input v-model.number="b.from_amount" type="number" min="0" :disabled="!setup.can_edit || i > 0" class="form-input w-full text-right tabular" :aria-label="`Band ${i + 1} from`" /></td>
									<td class="py-1 pr-2"><input v-model.number="b.to_amount" type="number" min="0" :disabled="!setup.can_edit" class="form-input w-full text-right tabular"
										:placeholder="i === slab.bands.length - 1 ? 'and above' : ''" :aria-label="`Band ${i + 1} up to`" @input="chain(i)" /></td>
									<td class="py-1 pr-2"><div class="flex items-center gap-1"><input v-model.number="b.percent" type="number" min="0" max="100" step="0.5" :disabled="!setup.can_edit" class="form-input w-20 text-right tabular" :aria-label="`Band ${i + 1} rate`" />%</div></td>
									<td class="py-1 text-right"><button v-if="setup.can_edit && slab.bands.length > 1" class="rounded p-1.5 text-gray-500 hover:bg-red-50 hover:text-red-600" :aria-label="`Remove band ${i + 1}`" @click="removeBand(i)"><FeatherIcon name="x" class="h-4 w-4" /></button></td>
								</tr>
							</tbody>
						</table>
						<Button v-if="setup.can_edit" class="mt-2" size="sm" variant="ghost" icon-left="plus" label="Add band" @click="addBand" />
					</div>
					<div>
						<h3 class="font-semibold">On top of the tax</h3>
						<p class="mb-2 text-xs text-gray-500">A percentage of the tax itself, such as the 3% AIDS levy.</p>
						<div v-for="(c, i) in slab.charges" :key="i" class="mb-1 flex items-center gap-2">
							<input v-model="c.description" :disabled="!setup.can_edit" class="form-input min-w-0 flex-1" placeholder="e.g. AIDS levy" aria-label="Charge" />
							<input v-model.number="c.percent" type="number" min="0" step="0.5" :disabled="!setup.can_edit" class="form-input w-20 text-right tabular" aria-label="Percent of the tax" />%
							<button v-if="setup.can_edit" class="rounded p-1.5 text-gray-500 hover:bg-red-50 hover:text-red-600" aria-label="Remove charge" @click="slab.charges.splice(i, 1)"><FeatherIcon name="x" class="h-4 w-4" /></button>
						</div>
						<Button v-if="setup.can_edit" size="sm" variant="ghost" icon-left="plus" label="Add" @click="slab.charges.push({ description: '', percent: null })" />
					</div>
					<label class="flex items-center gap-2 text-sm"><input v-model="slab.allow_tax_exemption" type="checkbox" :true-value="1" :false-value="0" :disabled="!setup.can_edit" class="form-checkbox" />
						Deductions marked "comes off before tax" (e.g. pension) reduce taxable pay</label>
					<p v-if="currentSlab?.people.length" class="rounded bg-blue-50 px-3 py-2 text-sm text-blue-900">
						{{ currentSlab.people.length }} {{ currentSlab.people.length === 1 ? "person is" : "people are" }} taxed on these bands. Saving changes makes a new version, and you choose when they move to it.
					</p>
				</section>

				<div v-if="slab" class="space-y-4 lg:col-start-2 xl:col-start-auto xl:sticky xl:top-20">
					<SamplePayslip :draft-slab="slab" :slab-name="slab.original" :structures="activeStructures" :default-structure="taxStructure" />
				</div>

				<footer v-if="slab && setup.can_edit" class="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 rounded-lg border bg-white px-4 py-3 shadow-sm lg:col-span-2 xl:col-span-3">
					<span class="mr-auto text-sm text-gray-500">{{ slabDirty ? "Not saved yet." : "No changes." }}</span>
					<Button label="Undo changes" :disabled="!slabDirty" @click="openSlab(currentSlab)" />
					<Button variant="solid" :label="currentSlab?.in_use ? 'Save as new version' : 'Save'" :disabled="!slabDirty || !slab.name" :loading="saving" @click="saveSlab" />
				</footer>
			</div>
		</div>

		<ComponentDialog :open="componentOpen" :component="editingComponent" :preset-kind="componentKind" @close="componentOpen = false" @saved="componentSaved" />
		<MovePeopleDialog v-if="move" :open="!!move" :kind="move.kind" :from="move.from" :to="move.to" @close="move = null" @moved="moved" />
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { LoadingIndicator } from "frappe-ui"
import { date } from "@/utils/format"
import { pay, ok, fail } from "../api"
import PageHeader from "../components/PageHeader.vue"
import Chips from "../components/Chips.vue"
import StructureEditor from "../components/StructureEditor.vue"
import SamplePayslip from "../components/SamplePayslip.vue"
import ComponentDialog from "../components/ComponentDialog.vue"
import MovePeopleDialog from "../components/MovePeopleDialog.vue"

const route = useRoute()
const router = useRouter()
const tab = ref(["components", "tax"].includes(route.query.tab) ? route.query.tab : "structures")
watch(tab, (t) => router.replace({ query: { ...route.query, tab: t } }))

const setup = ref(null)
const draft = ref(null) // {name, original, rows}
const slab = ref(null) // {name, original, effective_from, bands, charges, allow_tax_exemption}
const saving = ref(false)
const move = ref(null)
const componentOpen = ref(false)
const editingComponent = ref(null)
const componentKind = ref("earning")
let addToStructure = false

const clone = (x) => JSON.parse(JSON.stringify(x))
const strip = (rows) => rows.map(({ _key, ...r }) => r)
const current = computed(() => setup.value?.structures.find((s) => s.name === draft.value?.original))
const currentSlab = computed(() => setup.value?.slabs.find((s) => s.name === slab.value?.original))
const activeSlabs = computed(() => setup.value?.slabs.filter((s) => !s.disabled) || [])
const activeStructures = computed(() => setup.value?.structures.filter((s) => s.is_active === "Yes") || [])
// the sample for tax bands uses the structure most people are paid on
const taxStructure = computed(() => [...activeStructures.value].filter((s) => s.rows.some((r) => r.method === "tax"))
	.sort((a, b) => b.people.length - a.people.length)[0]?.name || activeStructures.value[0]?.name)
const draftPayload = computed(() => draft.value && { rows: strip(draft.value.rows) })
const dirty = computed(() => !!draft.value && (!current.value || draft.value.name !== current.value.name ||
	JSON.stringify(strip(draft.value.rows)) !== JSON.stringify(current.value.rows)))
const slabFields = (s) => JSON.stringify({ n: s.name, e: s.effective_from, b: s.bands, c: s.charges, a: s.allow_tax_exemption })
const slabDirty = computed(() => !!slab.value && (!currentSlab.value || slabFields(slab.value) !== slabFields({ ...currentSlab.value, name: currentSlab.value.name })))

function openStructure(s) {
	draft.value = s ? { name: s.name, original: s.name, rows: clone(s.rows) } : null
}
function newStructure() {
	const from = current.value || activeStructures.value[0]
	draft.value = { name: "", original: null, rows: from ? clone(from.rows) : [] }
}
function openSlab(s) {
	slab.value = s ? { ...clone(s), original: s.name } : null
}
function newSlab() {
	const from = currentSlab.value || activeSlabs.value[0]
	slab.value = { name: "", original: null, effective_from: `${new Date().getFullYear() + 1}-01-01`, allow_tax_exemption: 1,
		bands: from ? clone(from.bands) : [{ from_amount: 0, to_amount: null, percent: 0 }], charges: from ? clone(from.charges) : [] }
}

// a band starts where the one before it ends
function chain(i) {
	const next = slab.value.bands[i + 1]
	if (next) next.from_amount = slab.value.bands[i].to_amount || 0
}
function addBand() {
	const last = slab.value.bands[slab.value.bands.length - 1]
	if (!last.to_amount) last.to_amount = (last.from_amount || 0) + 1000
	slab.value.bands.push({ from_amount: last.to_amount, to_amount: null, percent: last.percent })
}
function removeBand(i) {
	slab.value.bands.splice(i, 1)
	if (i < slab.value.bands.length) slab.value.bands[i].from_amount = i ? slab.value.bands[i - 1].to_amount : 0
	else slab.value.bands[i - 1].to_amount = null
}

const kindLabel = (c) => (c.type === "Earning" ? "Earning" : c.do_not_include_in_total ? "Employer cost" : "Deduction")
function flags(c) {
	return [
		c.variable_based_on_taxable_salary && "From the tax bands",
		c.type === "Earning" && (c.is_tax_applicable ? "Taxable" : "Not taxed"),
		c.exempted_from_income_tax && "Before tax",
		c.depends_on_payment_days && "Less for unpaid days",
	].filter(Boolean).join(" · ")
}

function openComponent(c, kind = "earning", forStructure = false) {
	editingComponent.value = c
	componentKind.value = kind
	addToStructure = forStructure
	componentOpen.value = true
}
function componentSaved(s, name, kind) {
	setup.value = { ...s, structures: setup.value.structures, slabs: setup.value.slabs }
	componentOpen.value = false
	if (addToStructure && draft.value && !draft.value.rows.some((r) => r.component === name)) {
		const c = s.components.find((x) => x.name === name)
		draft.value.rows.push({ _key: `new-${name}`, kind, component: name, method: "fixed", of: "base", amount: null, rate: null, cap: null, formula: "",
			depends_on_payment_days: c.depends_on_payment_days, is_tax_applicable: kind === "earning" ? c.is_tax_applicable : 0,
			exempted_from_income_tax: kind === "deduction" ? c.exempted_from_income_tax : 0 })
	}
}

async function load(keep) {
	setup.value = await pay("get_pay_setup")
	const s = setup.value.structures.find((x) => x.name === keep?.structure) || activeStructures.value.find((x) => x.rows.some((r) => r.method === "tax")) || setup.value.structures[0]
	openStructure(s)
	openSlab(setup.value.slabs.find((x) => x.name === keep?.slab) || activeSlabs.value[0] || setup.value.slabs[0])
}

async function saveStructure() {
	saving.value = true
	try {
		const out = await pay("save_structure", { structure: { name: draft.value.name, original: draft.value.original, rows: strip(draft.value.rows) } })
		ok(out.versioned_from ? `Saved as ${out.name}` : `Saved ${out.name}`, out.versioned_from ? `${out.versioned_from} is unchanged` : "")
		await load({ structure: out.name, slab: slab.value?.original })
		if (out.versioned_from && out.people.length) move.value = { kind: "structure", from: out.versioned_from, to: out.name }
	} catch (e) {
		fail(e, "Not saved")
	} finally {
		saving.value = false
	}
}

async function saveSlab() {
	saving.value = true
	try {
		const out = await pay("save_slab", { slab: slab.value })
		ok(out.versioned_from ? `Saved as ${out.name}` : `Saved ${out.name}`)
		await load({ structure: draft.value?.original, slab: out.name })
		if (out.versioned_from && out.people.length) move.value = { kind: "slab", from: out.versioned_from, to: out.name }
	} catch (e) {
		fail(e, "Not saved")
	} finally {
		saving.value = false
	}
}

async function setActive(active) {
	try {
		setup.value = await pay("set_active", { name: current.value.name, active })
		ok(active ? `${current.value.name} is back` : `${current.value.name} retired`)
	} catch (e) {
		fail(e, active ? "Not brought back" : "Not retired")
	}
}

function moved() {
	move.value = null
	load({ structure: draft.value?.original, slab: slab.value?.original })
}

load().catch((e) => fail(e, "Could not load pay setup"))
</script>
