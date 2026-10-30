<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Admin" subtitle="Users, who can open what, item prices, and data import and export" />

		<div class="mx-auto w-full max-w-[1400px] space-y-4 p-4 lg:p-6">
			<div v-if="!home" class="p-10 text-center"><LoadingIndicator class="inline h-5 w-5 text-gray-500" /></div>
			<template v-else>
				<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
					<Tile to="/users" label="Enabled users" :value="home.users" :hint="`${home.disabled} disabled`" />
					<Tile to="/inspector" label="Users missing app access" :value="home.gaps.length"
						:hint="home.gaps.length ? 'They have a role for an app but can\'t read what it shows' : 'Everyone can read what their apps show'"
						:tone="home.gaps.length ? 'amber' : ''" />
					<Tile :to="{ path: '/prices', query: { missing: home.selling_price_list } }" label="Sales items with no selling price"
						:value="home.without_price ?? '—'" :hint="home.selling_price_list ? `in ${home.selling_price_list}` : 'No default selling price list'" />
					<Tile to="/prices/import" label="Last price import" :value="home.last_import ? home.last_import.created + home.last_import.updated : '—'"
						:hint="home.last_import ? `${home.last_import.by_name} · ${relative(home.last_import.when)}` : 'None yet'" />
				</div>

				<section v-if="home.gaps.length" class="rounded-lg border bg-white">
					<h3 class="border-b px-4 py-3 font-semibold">Missing app access</h3>
					<ul class="divide-y">
						<li v-for="g in home.gaps" :key="g.name" class="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
							<router-link :to="`/users/${encodeURIComponent(g.name)}`" class="min-w-0 flex-1 font-medium hover:underline">{{ g.full_name }}</router-link>
							<router-link v-for="a in g.apps" :key="a.key" :to="{ path: '/inspector', query: { user: g.name, app: a.key } }"
								class="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs text-amber-900 hover:bg-amber-100">
								{{ a.label }}: can't read {{ a.missing.length }}
							</router-link>
						</li>
					</ul>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { h, ref } from "vue"
import { RouterLink } from "vue-router"
import { LoadingIndicator } from "frappe-ui"
import PageHeader from "@/hr/components/PageHeader.vue"
import { relative } from "@/utils/format"
import { adm, fail } from "../api"

const home = ref(null)
adm("get_home").then((d) => (home.value = d)).catch((e) => fail(e, "Could not load"))

const Tile = (p) =>
	h(RouterLink, { to: p.to, class: ["block rounded-lg border bg-white p-4 hover:border-gray-400", p.tone === "amber" ? "border-amber-300" : ""] }, () => [
		h("div", { class: "text-sm text-gray-500" }, p.label),
		h("div", { class: "mt-1 text-2xl font-semibold tabular" }, String(p.value)),
		h("div", { class: "mt-1 truncate text-xs text-gray-500" }, p.hint),
	])
Tile.props = ["to", "label", "value", "hint", "tone"]
</script>
