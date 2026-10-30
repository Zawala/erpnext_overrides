<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Users" :subtitle="data ? `${data.total} users` : ''">
			<Button variant="solid" icon-left="plus" label="New user" @click="openNew" />
		</PageHeader>

		<div class="mx-auto w-full max-w-[1400px] space-y-3 p-4 lg:p-6">
			<div class="flex flex-wrap items-center gap-2">
				<input v-model="search" class="form-input w-full sm:w-72" placeholder="Search name or email" aria-label="Search users" />
				<Chips v-model="enabled" :options="[{ value: '1', label: 'Enabled' }, { value: '0', label: 'Disabled' }, { value: '', label: 'All' }]" />
				<select v-model="role" class="form-select w-full sm:w-56" aria-label="Filter by role">
					<option value="">Any role</option>
					<option v-for="r in roles" :key="r" :value="r">{{ r }}</option>
				</select>
			</div>

			<div v-if="!data" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<div v-else class="overflow-x-auto rounded-lg border bg-white">
				<table class="w-full text-sm">
					<thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
						<tr>
							<th class="px-4 py-2 font-medium">User</th>
							<th class="px-2 py-2 font-medium">Role profiles</th>
							<th class="px-2 py-2 font-medium text-right">Roles</th>
							<th class="px-2 py-2 font-medium">Apps</th>
							<th class="px-4 py-2 font-medium">Last login</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="u in data.users" :key="u.name" class="cursor-pointer border-t hover:bg-gray-50" :class="!u.enabled && 'text-gray-400'"
							@click="$router.push(`/users/${encodeURIComponent(u.name)}`)">
							<td class="px-4 py-2">
								<div class="font-medium">{{ u.full_name }} <span v-if="!u.enabled" class="ml-1 rounded bg-gray-100 px-1.5 text-xs">Disabled</span>
									<span v-if="u.user_type !== 'System User'" class="ml-1 rounded bg-gray-100 px-1.5 text-xs">{{ u.user_type }}</span></div>
								<div class="text-xs text-gray-500">{{ u.name }}</div>
							</td>
							<td class="px-2 py-2">{{ u.role_profiles.join(", ") || "—" }}</td>
							<td class="px-2 py-2 text-right tabular">{{ u.roles }}</td>
							<td class="px-2 py-2">
								<span v-for="a in u.apps" :key="a.key" class="mr-1 inline-block rounded-full px-2 py-0.5 text-xs"
									:class="a.missing.length ? 'bg-amber-50 text-amber-900' : 'bg-gray-100 text-gray-700'"
									:title="a.missing.length ? `Can't read: ${a.missing.join(', ')}` : ''">
									{{ a.label }}<template v-if="a.missing.length"> · {{ a.missing.length }} missing</template>
								</span>
							</td>
							<td class="px-4 py-2 text-gray-500">{{ u.last_login ? relative(u.last_login) : "Never" }}</td>
						</tr>
					</tbody>
				</table>
				<div v-if="data.users.length < data.total" class="border-t p-2 text-center">
					<Button label="Load more" :loading="loading" @click="load(true)" />
				</div>
			</div>
		</div>

		<Dialog v-model="newOpen" :options="{ title: 'New user', size: 'lg' }">
			<template #body-content>
				<div class="space-y-4">
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<label><span class="mb-1.5 block text-sm text-gray-600">First name</span><input v-model="form.first_name" class="form-input w-full" /></label>
						<label><span class="mb-1.5 block text-sm text-gray-600">Last name</span><input v-model="form.last_name" class="form-input w-full" /></label>
						<label class="sm:col-span-2"><span class="mb-1.5 block text-sm text-gray-600">Email</span><input v-model="form.email" type="email" class="form-input w-full" /></label>
					</div>
					<div>
						<div class="mb-1.5 text-sm text-gray-600">Role profiles <span class="text-gray-400">— the roles then come from these</span></div>
						<div class="flex flex-wrap gap-2">
							<label v-for="p in profiles" :key="p" class="flex items-center gap-1.5 rounded border px-2 py-1 text-sm">
								<input v-model="form.profiles" type="checkbox" class="form-checkbox" :value="p" /> {{ p }}
							</label>
						</div>
					</div>
					<div v-if="!form.profiles.length">
						<div class="mb-1.5 text-sm text-gray-600">Or roles, one by one</div>
						<div class="grid max-h-48 grid-cols-1 gap-1 overflow-y-auto rounded border p-2 sm:grid-cols-2">
							<label v-for="r in roles" :key="r" class="flex items-center gap-1.5 text-sm">
								<input v-model="form.roles" type="checkbox" class="form-checkbox" :value="r" /> {{ r }}
							</label>
						</div>
					</div>
					<label class="flex items-center gap-2 text-sm"><input v-model="form.send_welcome_email" type="checkbox" class="form-checkbox" /> Send a welcome email to set a password</label>
				</div>
			</template>
			<template #actions>
				<Button variant="solid" class="w-full" label="Create user" :loading="saving" :disabled="!form.email || !form.first_name" @click="create" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { ref, reactive, watch } from "vue"
import { useRouter } from "vue-router"
import { Dialog, LoadingIndicator, call, debounce } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import Chips from "@/hr/components/Chips.vue"
import { relative } from "@/utils/format"
import { adm, fail, ok } from "../api"

const router = useRouter()
const data = ref(null)
const search = ref("")
const enabled = ref("1")
const role = ref("")
const loading = ref(false)
const roles = ref([])
// get_list ignores pluck on some versions and returns [{name}]
const names = (rows) => rows.map((r) => (typeof r === "string" ? r : r.name))
const profiles = ref([])

async function load(more = false) {
	loading.value = true
	try {
		const res = await adm("get_users", { search: search.value, enabled: enabled.value, role: role.value,
			start: more ? data.value.users.length : 0 })
		data.value = more ? { ...res, users: [...data.value.users, ...res.users] } : res
	} catch (e) {
		fail(e, "Could not load users")
	} finally {
		loading.value = false
	}
}
watch([enabled, role], () => load())
watch(search, debounce(() => load(), 300))
load()

call("frappe.client.get_list", { doctype: "Role", filters: { disabled: 0, desk_access: 1 }, pluck: "name", limit_page_length: 0, order_by: "name asc" })
	.then((r) => (roles.value = names(r).filter((x) => !["All", "Guest", "Administrator", "Desk User"].includes(x))))
call("frappe.client.get_list", { doctype: "Role Profile", pluck: "name", limit_page_length: 0, order_by: "name asc" }).then((r) => (profiles.value = names(r)))

const newOpen = ref(false)
const saving = ref(false)
const form = reactive({ first_name: "", last_name: "", email: "", profiles: [], roles: [], send_welcome_email: true })
function openNew() {
	Object.assign(form, { first_name: "", last_name: "", email: "", profiles: [], roles: [], send_welcome_email: true })
	newOpen.value = true
}
async function create() {
	saving.value = true
	try {
		const u = await adm("create_user", { ...form, send_welcome_email: form.send_welcome_email ? 1 : 0 })
		ok("User created", u.full_name)
		newOpen.value = false
		router.push(`/users/${encodeURIComponent(u.name)}`)
	} catch (e) {
		fail(e, "User not created")
	} finally {
		saving.value = false
	}
}
</script>
