<template>
	<div class="h-full overflow-y-auto">
		<PageHeader :title="u?.full_name || user" :subtitle="u ? `${u.name} · ${u.user_type}` : ''" back="/users">
			<template v-if="u" #badge>
				<span class="rounded px-1.5 text-xs" :class="u.enabled ? 'bg-green-50 text-green-800' : 'bg-gray-100 text-gray-600'">{{ u.enabled ? "Enabled" : "Disabled" }}</span>
			</template>
			<template v-if="u && !u.standard">
				<Button :label="u.enabled ? 'Disable' : 'Enable'" :disabled="u.is_self" @click="confirmEnable = true" />
				<Button icon-left="shield" label="Inspect access" @click="$router.push({ path: '/inspector', query: { user: u.name } })" />
			</template>
		</PageHeader>

		<div v-if="!u" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
		<div v-else class="mx-auto grid w-full max-w-[1600px] grid-cols-1 items-start gap-4 p-4 pb-28 lg:grid-cols-[minmax(0,1fr)_380px] lg:p-6 lg:pb-28">
			<div class="space-y-4">
				<!-- App access -->
				<section v-if="u.apps.length" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Apps</h3>
					<ul class="divide-y">
						<li v-for="a in u.apps" :key="a.key" class="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
							<span class="w-32 font-medium">{{ a.label }}</span>
							<span v-if="!a.missing.length" class="text-green-700">Can read everything it shows</span>
							<template v-else>
								<span class="text-amber-800">Can't read {{ a.missing.join(", ") }}</span>
								<router-link class="ml-auto text-blue-700 hover:underline" :to="{ path: '/inspector', query: { user: u.name, app: a.key } }">See fixes →</router-link>
							</template>
						</li>
					</ul>
				</section>

				<!-- Role profiles -->
				<section class="rounded-lg border bg-white">
					<header class="border-b px-4 py-3">
						<h3 class="font-semibold">Role profiles</h3>
						<p class="text-xs text-gray-500">A profile is a bundle of roles. While a user has profiles, their roles are exactly the profiles' roles.</p>
					</header>
					<div class="flex flex-wrap gap-2 p-4">
						<label v-for="p in u.all_profiles" :key="p.name" class="flex cursor-pointer items-center gap-1.5 rounded border px-2.5 py-1 text-sm"
							:class="profileDirty(p.name) ? 'border-blue-400 bg-blue-50' : ''" :title="p.roles.join(', ')">
							<input v-model="profiles" type="checkbox" class="form-checkbox" :value="p.name" :disabled="u.standard" /> {{ p.name }}
							<span class="text-xs text-gray-400">{{ p.roles.length }}</span>
						</label>
					</div>
					<div v-if="profilesChanged" class="flex justify-end gap-2 border-t px-4 py-2">
						<Button label="Undo" @click="profiles = [...u.role_profiles]" />
						<Button variant="solid" label="Review change" @click="reviewProfiles" />
					</div>
				</section>

				<!-- Roles -->
				<section class="rounded-lg border bg-white">
					<header class="border-b px-4 py-3">
						<h3 class="font-semibold">Roles <span class="font-normal text-gray-500">· {{ u.roles.length }}</span></h3>
						<p v-if="u.roles_from_profiles" class="text-xs text-amber-800">
							These come from {{ u.role_profiles.join(", ") }}. Change the profiles above, or untick them all to set roles by hand.
						</p>
					</header>
					<div v-for="g in roleGroups" :key="g.label" class="px-4 py-3">
						<div class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">{{ g.label }}</div>
						<div class="grid grid-cols-1 gap-1 sm:grid-cols-2 xl:grid-cols-3">
							<label v-for="r in g.roles" :key="r" class="flex items-center gap-2 rounded px-1 py-0.5 text-sm"
								:class="[roleDirty(r) ? 'bg-blue-50 font-medium text-blue-800' : '', u.roles_from_profiles || u.standard ? 'opacity-70' : 'cursor-pointer']">
								<input type="checkbox" class="form-checkbox" :checked="hasRole(r)" :disabled="u.roles_from_profiles || u.standard" @change="toggle(r)" /> {{ r }}
							</label>
						</div>
					</div>
				</section>

				<!-- User Permissions -->
				<section class="rounded-lg border bg-white">
					<header class="flex items-center border-b px-4 py-3">
						<div class="flex-1">
							<h3 class="font-semibold">User Permissions</h3>
							<p class="text-xs text-gray-500">Limit which records the user sees, e.g. only one Company. Add them in desk.</p>
						</div>
						<a :href="`/app/user-permission/new?user=${encodeURIComponent(u.name)}`" target="_blank" class="text-sm text-blue-700 hover:underline">Add in desk ↗</a>
					</header>
					<p v-if="!u.user_permissions.length" class="px-4 py-4 text-sm text-gray-500">None: the user sees every record their roles allow.</p>
					<table v-else class="w-full text-sm">
						<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
							<tr><th class="px-4 py-2 font-medium">Only</th><th class="px-2 py-2 font-medium">Applies to</th><th /></tr>
						</thead>
						<tbody>
							<tr v-for="p in u.user_permissions" :key="p.name" :id="`up-${p.name}`" class="border-t" :class="highlight === p.name ? 'bg-amber-50' : ''">
								<td class="px-4 py-2">{{ p.allow }} = <b class="font-medium">{{ p.for_value }}</b><span v-if="p.is_default" class="ml-1 text-xs text-gray-500">(default)</span></td>
								<td class="px-2 py-2 text-gray-600">{{ p.apply_to_all_doctypes ? "Every document type" : p.applicable_for }}</td>
								<td class="px-4 py-2 text-right"><button class="text-xs text-red-700 hover:underline" @click="removing = p">Remove</button></td>
							</tr>
						</tbody>
					</table>
				</section>
			</div>

			<!-- History -->
			<section class="rounded-lg border bg-white lg:sticky lg:top-20">
				<h3 class="border-b px-4 py-3 font-semibold">Who changed what</h3>
				<p v-if="!u.history.length" class="px-4 py-6 text-sm text-gray-500">No changes recorded yet.</p>
				<ul v-else class="max-h-[70vh] divide-y overflow-y-auto">
					<li v-for="(h, i) in u.history" :key="i" class="px-4 py-2.5 text-sm">
						<div v-for="l in h.lines" :key="l" :class="l.startsWith('+') ? 'text-green-800' : l.startsWith('−') ? 'text-red-800' : ''">{{ l }}</div>
						<div class="text-xs text-gray-500">{{ h.by }} · {{ relative(h.when) }}</div>
					</li>
				</ul>
			</section>
		</div>

		<!-- Save bar for roles -->
		<div v-if="adding.length || dropping.length" class="fixed inset-x-0 bottom-14 z-30 border-t bg-white px-4 py-3 shadow-lg md:bottom-0 md:left-56 lg:left-60">
			<div class="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
				<div class="min-w-0 flex-1 text-sm">
					<b>{{ u.full_name }}</b>:
					<span v-for="r in adding" :key="r" class="ml-1 text-green-800">+ {{ r }}</span>
					<span v-for="r in dropping" :key="r" class="ml-1 text-red-800">− {{ r }}</span>
				</div>
				<Button label="Discard" @click="resetRoles" />
				<Button variant="solid" :label="`Save ${adding.length + dropping.length} role change${adding.length + dropping.length === 1 ? '' : 's'}`" :loading="saving" @click="saveRoles" />
			</div>
		</div>

		<Dialog v-model="profileOpen" :options="{ title: `Role profiles for ${u?.full_name}`, size: 'lg' }">
			<template #body-content>
				<div v-if="preview" class="space-y-3 text-sm">
					<p>Profiles: <s v-if="u.role_profiles.length" class="text-gray-500">{{ u.role_profiles.join(", ") }}</s> → <b>{{ profiles.join(", ") || "none (roles stay as they are, editable by hand)" }}</b></p>
					<template v-if="profiles.length">
						<div v-if="preview.add.length"><div class="font-medium text-green-800">Roles added ({{ preview.add.length }})</div>{{ preview.add.join(", ") }}</div>
						<div v-if="preview.remove.length"><div class="font-medium text-red-800">Roles removed ({{ preview.remove.length }})</div>{{ preview.remove.join(", ") }}</div>
						<div class="text-gray-500">{{ preview.keep.length }} roles stay.</div>
					</template>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Set these profiles" :loading="saving" @click="saveProfiles" />
			</template>
		</Dialog>

		<Dialog v-model="confirmEnable" :options="{ title: u?.enabled ? `Disable ${u?.full_name}?` : `Enable ${u?.full_name}?`, size: 'sm' }">
			<template #body-content>
				<p class="text-sm">{{ u?.enabled ? "They are logged out and can't log in until enabled again. Nothing they made is deleted." : "They can log in again with their existing password." }}</p>
			</template>
			<template #actions>
				<Button variant="solid" :theme="u?.enabled ? 'red' : 'gray'" class="w-full" :label="u?.enabled ? 'Disable' : 'Enable'" :loading="saving" @click="toggleEnabled" />
			</template>
		</Dialog>

		<Dialog :model-value="!!removing" :options="{ title: 'Remove this User Permission?', size: 'sm' }" @update:model-value="removing = null">
			<template #body-content>
				<p v-if="removing" class="text-sm">{{ u.full_name }} will no longer be limited to {{ removing.allow }} <b>{{ removing.for_value }}</b>
					{{ removing.apply_to_all_doctypes ? "anywhere" : `on ${removing.applicable_for}` }}, and will see every record their roles allow.</p>
			</template>
			<template #actions>
				<Button variant="solid" theme="red" class="w-full" label="Remove" :loading="saving" @click="removePermission" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, nextTick, ref } from "vue"
import { useRoute } from "vue-router"
import { Dialog, LoadingIndicator } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import { relative } from "@/utils/format"
import { adm, fail, ok } from "../api"

const props = defineProps({ user: String })
const route = useRoute()
const u = ref(null)
const staged = ref(new Set()) // roles ticked as the user will have them
const profiles = ref([])
const saving = ref(false)
const highlight = ref(route.query.restriction || "")

function setUser(d) {
	u.value = d
	staged.value = new Set(d.roles)
	profiles.value = [...d.role_profiles]
}
async function load() {
	try {
		setUser(await adm("get_user", { user: props.user }))
		if (highlight.value) nextTick(() => document.getElementById(`up-${highlight.value}`)?.scrollIntoView({ block: "center" }))
	} catch (e) {
		fail(e, "Could not load the user")
	}
}
load()

const roleGroups = computed(() => {
	if (!u.value) return []
	const app = u.value.app_roles.filter((r) => u.value.all_roles.includes(r))
	return [{ label: "App roles", roles: app }, { label: "Other roles", roles: u.value.all_roles.filter((r) => !app.includes(r)) }]
})
const hasRole = (r) => staged.value.has(r)
const roleDirty = (r) => staged.value.has(r) !== u.value.roles.includes(r)
const adding = computed(() => (u.value ? [...staged.value].filter((r) => !u.value.roles.includes(r)) : []))
const dropping = computed(() => (u.value ? u.value.roles.filter((r) => !staged.value.has(r)) : []))
function toggle(r) {
	const s = new Set(staged.value)
	s.has(r) ? s.delete(r) : s.add(r)
	staged.value = s
}
const resetRoles = () => (staged.value = new Set(u.value.roles))

async function saveRoles() {
	saving.value = true
	try {
		setUser(await adm("save_roles", { user: u.value.name, add: adding.value, remove: dropping.value }))
		ok("Roles saved")
	} catch (e) {
		fail(e, "Roles not saved")
	} finally {
		saving.value = false
	}
}

const profileDirty = (p) => profiles.value.includes(p) !== u.value.role_profiles.includes(p)
const profilesChanged = computed(() => u.value && u.value.all_profiles.some((p) => profileDirty(p.name)))
const profileOpen = ref(false)
const preview = ref(null)
async function reviewProfiles() {
	try {
		preview.value = await adm("preview_role_profiles", { user: u.value.name, profiles: profiles.value })
		profileOpen.value = true
	} catch (e) {
		fail(e)
	}
}
async function saveProfiles() {
	saving.value = true
	try {
		setUser(await adm("set_role_profiles", { user: u.value.name, profiles: profiles.value }))
		profileOpen.value = false
		ok("Role profiles saved")
	} catch (e) {
		fail(e, "Profiles not saved")
	} finally {
		saving.value = false
	}
}

const confirmEnable = ref(false)
async function toggleEnabled() {
	saving.value = true
	try {
		setUser(await adm("set_enabled", { user: u.value.name, enabled: u.value.enabled ? 0 : 1 }))
		confirmEnable.value = false
		ok(u.value.enabled ? "Enabled" : "Disabled", u.value.full_name)
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}

const removing = ref(null)
async function removePermission() {
	saving.value = true
	try {
		setUser(await adm("remove_user_permission", { name: removing.value.name }))
		removing.value = null
		ok("User Permission removed")
	} catch (e) {
		fail(e)
	} finally {
		saving.value = false
	}
}
</script>
