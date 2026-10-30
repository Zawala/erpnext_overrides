<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Permission inspector" subtitle="What a user can do on a document type, why not, and the smallest fix" />

		<div class="mx-auto w-full max-w-[1400px] space-y-4 p-4 lg:p-6">
			<Chips v-model="mode" :options="[{ value: 'user', label: 'One user' }, { value: 'who', label: 'Who can\'t…' }]" />

			<!-- One user -->
			<template v-if="mode === 'user'">
				<div class="grid grid-cols-1 gap-3 rounded-lg border bg-white p-4 md:grid-cols-[1fr_1fr_auto]">
					<div><div class="mb-1.5 text-sm text-gray-600">User</div>
						<LinkField v-model="user" doctype="User" :filters="{ user_type: 'System User', name: ['not in', ['Administrator', 'Guest']] }" placeholder="Pick a user" /></div>
					<div>
						<div class="mb-1.5 text-sm text-gray-600">Check</div>
						<div class="flex flex-wrap gap-1.5">
							<button v-for="a in apps" :key="a.key" class="rounded-full border px-3 py-1 text-sm"
								:class="app === a.key ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white hover:bg-gray-50'" @click="pickApp(a.key)">{{ a.label }} app</button>
						</div>
						<div class="mt-2"><LinkField v-model="doctype" doctype="DocType" :filters="{ istable: 0 }" placeholder="…or one document type" @update:model-value="app = ''" /></div>
					</div>
					<div class="flex items-end"><Button variant="solid" label="Inspect" :loading="loading" :disabled="!user || (!app && !doctype)" @click="run" /></div>
				</div>

				<template v-if="result">
					<div v-for="n in result.notes" :key="n" class="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">{{ n }}</div>
					<p class="text-sm text-gray-600">
						<router-link :to="`/users/${encodeURIComponent(result.user.name)}`" class="font-medium hover:underline">{{ result.user.full_name }}</router-link>
						— {{ blocked.length ? `${blocked.length} of ${result.results.length} document types have something missing` : "has everything checked" }}.
					</p>

					<section v-for="r in sorted" :key="r.doctype" class="rounded-lg border bg-white">
						<header class="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
							<h3 class="flex-1 font-semibold">{{ r.doctype }}</h3>
							<span v-for="p in r.perms" :key="p.ptype" class="rounded px-1.5 py-0.5 text-xs"
								:class="!p.allowed ? 'bg-red-50 text-red-800' : p.only_own ? 'bg-amber-50 text-amber-900' : 'bg-green-50 text-green-800'"
								:title="p.only_own ? 'Only documents they created' : ''">
								{{ p.allowed ? "✓" : "✗" }} {{ PTYPE_LABELS[p.ptype] }}{{ p.only_own ? " (own)" : "" }}
							</span>
						</header>

						<div v-if="r.restrictions.length" class="border-b px-4 py-2 text-sm">
							<span class="text-gray-600">Limited by User Permissions:</span>
							<router-link v-for="x in r.restrictions" :key="x.name" class="ml-2 text-blue-700 hover:underline"
								:to="{ path: `/users/${encodeURIComponent(result.user.name)}`, query: { restriction: x.name } }">only {{ x.allow }} = {{ x.for_value }}</router-link>
						</div>

						<div v-for="group in fixGroups(r)" :key="group.key" class="border-b px-4 py-3 last:border-b-0">
							<div class="text-sm"><b class="font-medium">Can't {{ group.ptypes.map((p) => PTYPE_LABELS[p].toLowerCase()).join(", ") }}.</b></div>
							<details v-if="group.why.length" class="mt-1 text-xs text-gray-500">
								<summary class="cursor-pointer">Why</summary>
								<div v-for="w in group.why" :key="w">{{ w }}</div>
							</details>
							<div class="mt-2 flex flex-wrap gap-2">
								<template v-for="f in group.fixes" :key="f.text">
									<Button v-if="f.kind === 'role' || f.kind === 'profile'" size="sm" :label="f.text" @click="propose(f, r.doctype, group.ptypes)">
										<template #suffix><span v-if="f.kind === 'role'" class="text-xs text-gray-500">· opens {{ f.also }} types</span></template>
									</Button>
									<a v-else-if="f.link" :href="f.link" target="_blank" class="text-sm text-blue-700 hover:underline">{{ f.text }} ↗</a>
									<router-link v-else :to="`/users/${encodeURIComponent(result.user.name)}`" class="text-sm text-blue-700 hover:underline">{{ f.text }}</router-link>
								</template>
							</div>
						</div>
					</section>
				</template>
			</template>

			<!-- Who can't -->
			<template v-else>
				<div class="grid grid-cols-1 gap-3 rounded-lg border bg-white p-4 md:grid-cols-[1fr_200px_auto]">
					<div><div class="mb-1.5 text-sm text-gray-600">Document type</div><LinkField v-model="whoDoctype" doctype="DocType" :filters="{ istable: 0 }" /></div>
					<label><span class="mb-1.5 block text-sm text-gray-600">Can't</span>
						<select v-model="whoPtype" class="form-select w-full"><option v-for="(l, k) in PTYPE_LABELS" :key="k" :value="k">{{ l }}</option></select></label>
					<div class="flex items-end"><Button variant="solid" label="List users" :loading="loading" :disabled="!whoDoctype" @click="runWho" /></div>
				</div>
				<div v-if="who" class="rounded-lg border bg-white">
					<p v-if="!who.length" class="px-4 py-4 text-sm text-gray-500">Every enabled user can {{ PTYPE_LABELS[whoPtype].toLowerCase() }} {{ whoDoctype }}.</p>
					<ul v-else class="divide-y">
						<li v-for="w in who" :key="w.name" class="flex items-center px-4 py-2 text-sm">
							<span class="flex-1">{{ w.full_name }} <span class="text-gray-500">{{ w.name }}</span></span>
							<button class="text-blue-700 hover:underline" @click="inspectFrom(w.name)">Inspect →</button>
						</li>
					</ul>
				</div>
			</template>
		</div>

		<Dialog v-model="confirmOpen" :options="{ title: 'Apply this fix?', size: 'lg' }">
			<template #body-content>
				<div v-if="fix" class="space-y-2 text-sm">
					<p v-if="fix.kind === 'role'">Give <b>{{ result.user.full_name }}</b> the role <b>{{ fix.role }}</b> so they can {{ fix.ptypes.map((p) => PTYPE_LABELS[p].toLowerCase()).join(", ") }} {{ fix.doctype }}.</p>
					<p v-else>Add the role profile <b>{{ fix.profile }}</b> to <b>{{ result.user.full_name }}</b> (it carries {{ fix.role }}).</p>
					<p v-if="fix.kind === 'role'" class="text-gray-600">{{ fix.role }} can read {{ fix.also }} document types in all; it may open more than {{ fix.doctype }}.</p>
					<template v-if="fix.preview">
						<div v-if="fix.preview.add.length"><span class="font-medium text-green-800">Roles added:</span> {{ fix.preview.add.join(", ") }}</div>
						<div v-if="fix.preview.remove.length"><span class="font-medium text-red-800">Roles removed:</span> {{ fix.preview.remove.join(", ") }}</div>
					</template>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Apply" :loading="saving" @click="apply" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRoute } from "vue-router"
import { Dialog } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import LinkField from "@/components/LinkField.vue"
import { adm, fail, ok, PTYPE_LABELS } from "../api"

const route = useRoute()
const mode = ref("user")
const user = ref(route.query.user || "")
const app = ref(route.query.app || "")
const doctype = ref(route.query.doctype || "")
const apps = ref([
	{ key: "sales", label: "Sales" }, { key: "hr", label: "HR admin" }, { key: "approvals", label: "HR approvals" },
	{ key: "accounts", label: "Accounts" }, { key: "stock", label: "Items and prices" },
])
const result = ref(null)
const loading = ref(false)

function pickApp(key) {
	app.value = app.value === key ? "" : key
	if (app.value) doctype.value = ""
}

async function run() {
	loading.value = true
	try {
		result.value = await adm("inspect", { user: user.value, doctype: app.value ? undefined : doctype.value, app: app.value || undefined })
		apps.value = result.value.apps
	} catch (e) {
		fail(e, "Could not inspect")
	} finally {
		loading.value = false
	}
}
if (user.value && (app.value || doctype.value)) run()

const missing = (r) => r.perms.filter((p) => !p.allowed)
const blocked = computed(() => (result.value?.results || []).filter((r) => missing(r).length))
const sorted = computed(() => [...(result.value?.results || [])].sort((a, b) => missing(b).length - missing(a).length))

/** Permission types with the same fixes are shown once ("Can't create, delete"). */
function fixGroups(r) {
	const groups = {}
	for (const p of missing(r)) {
		const key = JSON.stringify(p.fixes || [])
		const g = (groups[key] ||= { key, ptypes: [], why: [], fixes: p.fixes || [] })
		g.ptypes.push(p.ptype)
		for (const w of p.why || []) if (!g.why.includes(w)) g.why.push(w)
	}
	return Object.values(groups)
}

const confirmOpen = ref(false)
const fix = ref(null)
const saving = ref(false)
async function propose(f, dt, ptypes) {
	fix.value = { ...f, doctype: dt, ptypes }
	if (f.kind === "profile") {
		const u = await adm("get_user", { user: result.value.user.name })
		fix.value.profiles = [...u.role_profiles, f.profile]
		fix.value.preview = await adm("preview_role_profiles", { user: u.name, profiles: fix.value.profiles })
	}
	confirmOpen.value = true
}
async function apply() {
	saving.value = true
	try {
		if (fix.value.kind === "role") await adm("save_roles", { user: result.value.user.name, add: [fix.value.role], remove: [] })
		else await adm("set_role_profiles", { user: result.value.user.name, profiles: fix.value.profiles })
		ok("Fix applied", fix.value.kind === "role" ? `+ ${fix.value.role}` : `+ ${fix.value.profile}`)
		confirmOpen.value = false
		run()
	} catch (e) {
		fail(e, "Not applied")
	} finally {
		saving.value = false
	}
}

const whoDoctype = ref("")
const whoPtype = ref("read")
const who = ref(null)
async function runWho() {
	loading.value = true
	try {
		who.value = await adm("users_lacking", { doctype: whoDoctype.value, ptype: whoPtype.value })
	} catch (e) {
		fail(e)
	} finally {
		loading.value = false
	}
}
function inspectFrom(name) {
	user.value = name
	doctype.value = whoDoctype.value
	app.value = ""
	mode.value = "user"
	run()
}
</script>
