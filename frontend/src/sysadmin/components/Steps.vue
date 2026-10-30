<template>
	<!-- A step already done can be clicked to go back to it; later steps can't be skipped to -->
	<nav aria-label="Steps">
		<ol class="hidden sm:flex items-center gap-1 text-sm">
			<li v-for="(s, i) in steps" :key="s" class="flex items-center gap-1">
				<button class="flex items-center gap-2 rounded-full px-2.5 py-1"
					:class="i === current ? 'bg-gray-900 text-white' : i < current ? 'text-gray-800 hover:bg-gray-100' : 'text-gray-400 cursor-default'"
					:disabled="i >= current || locked" :aria-current="i === current ? 'step' : undefined" @click="$emit('go', i)">
					<span class="grid h-5 w-5 place-items-center rounded-full text-xs"
						:class="i === current ? 'bg-white text-gray-900' : i < current ? 'bg-green-600 text-white' : 'border border-gray-300'">
						<FeatherIcon v-if="i < current" name="check" class="h-3 w-3" />
						<template v-else>{{ i + 1 }}</template>
					</span>
					{{ s }}
				</button>
				<FeatherIcon v-if="i < steps.length - 1" name="chevron-right" class="h-4 w-4 text-gray-300" />
			</li>
		</ol>
		<div class="sm:hidden">
			<div class="flex items-center justify-between text-sm">
				<button v-if="current > 0 && !locked" class="flex items-center gap-1 text-gray-600" @click="$emit('go', current - 1)">
					<FeatherIcon name="chevron-left" class="h-4 w-4" /> Back
				</button>
				<span v-else />
				<span class="text-gray-500">Step {{ current + 1 }} of {{ steps.length }} · <b class="font-medium text-gray-900">{{ steps[current] }}</b></span>
			</div>
			<div class="mt-2 h-1 rounded bg-gray-200"><div class="h-1 rounded bg-gray-900" :style="{ width: `${((current + 1) / steps.length) * 100}%` }" /></div>
		</div>
	</nav>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"

defineProps({ steps: Array, current: Number, locked: Boolean })
defineEmits(["go"])
</script>
