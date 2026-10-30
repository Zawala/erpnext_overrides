<template>
	<div>
		<!-- narrow screens scroll the chart sideways rather than shrink it to a strip; it opens on the latest months -->
		<div ref="box" class="overflow-x-auto">
		<svg :viewBox="`0 0 ${W} ${H}`" class="h-48 w-full min-w-[640px] sm:h-64" role="img" :aria-label="label">
			<g v-for="t in ticks" :key="t.v">
				<line :x1="PAD" :x2="W - 8" :y1="y(t.v)" :y2="y(t.v)" stroke="#e5e7eb" />
				<text :x="PAD - 6" :y="y(t.v) + 4" text-anchor="end" class="fill-gray-400 text-[11px]">{{ t.label }}</text>
			</g>
			<g v-for="(m, i) in months" :key="m.month">
				<rect v-for="(s, j) in series" :key="s.key" :x="x(i) + j * (bw + 2)" :y="y(m[s.key])" :width="bw" :height="y(0) - y(m[s.key])" :class="s.class">
					<title>{{ s.label }} {{ format(m[s.key]) }}</title>
				</rect>
				<text :x="x(i) + (series.length * (bw + 2) - 2) / 2" :y="H - 6" text-anchor="middle" class="fill-gray-500 text-[11px]">{{ monthLabel(m.month) }}</text>
			</g>
		</svg>
		</div>
		<div class="flex gap-4 text-xs text-gray-500">
			<span v-for="s in series" :key="s.key"><span class="mr-1 inline-block h-2.5 w-2.5" :class="s.swatch" />{{ s.label }}</span>
		</div>
	</div>
</template>

<script setup>
// Bars per month, one per series side by side: { key, label, class: "fill-green-500", swatch: "bg-green-500" } (both spelled out for Tailwind)
import { computed, onMounted, ref } from "vue"
const props = defineProps({
	months: { type: Array, required: true },
	series: { type: Array, required: true },
	label: String,
	// tooltip amounts; each app passes its own money formatter
	format: { type: Function, default: (v) => Number(v || 0).toLocaleString() },
})

const box = ref(null)
onMounted(() => box.value && (box.value.scrollLeft = box.value.scrollWidth))

const W = 900, H = 240, PAD = 64
const maxV = computed(() => Math.max(1, ...props.months.flatMap((m) => props.series.map((s) => m[s.key] || 0))))
const slot = computed(() => (W - PAD - 8) / (props.months.length || 12))
const bw = computed(() => Math.max(4, slot.value / props.series.length - 6))
const x = (i) => PAD + i * slot.value + (slot.value - props.series.length * (bw.value + 2) + 2) / 2
const y = (v) => 10 + (H - 40) * (1 - (v || 0) / maxV.value)
const ticks = computed(() => [0, 0.5, 1].map((f) => ({ v: maxV.value * f, label: short(maxV.value * f) })))
const short = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : v.toFixed(0))
const monthLabel = (m) => new Date(m + "-01T00:00:00").toLocaleDateString(undefined, { month: "short" })
</script>
