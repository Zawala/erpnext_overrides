<template>
	<Teleport to="body">
		<div v-if="open" class="fixed inset-0 z-50 flex items-stretch justify-center bg-black/40 md:p-6" @click.self="close">
			<div class="flex w-full max-w-6xl flex-col overflow-hidden bg-white md:rounded-xl md:shadow-2xl">
				<!-- Toolbar -->
				<header class="flex flex-wrap items-end gap-3 border-b px-4 py-3">
					<div class="mr-auto min-w-0">
						<h2 class="text-lg font-semibold">{{ title || "Print preview" }}</h2>
						<p class="truncate text-sm text-gray-500">{{ trial ? trial.note : `${doctype} · ${name}` }}</p>
					</div>
					<label class="w-full sm:w-auto">
						<span class="mb-1 block text-xs text-gray-500">Print format</span>
						<select v-model="format" class="form-select w-full sm:w-56" :disabled="!options">
							<option v-for="f in options?.formats || []" :key="f.name" :value="f.name">
								{{ f.name }}{{ f.name === options.default_format ? " (default)" : "" }}
							</option>
						</select>
					</label>
					<label class="w-full sm:w-auto">
						<span class="mb-1 block text-xs text-gray-500">Letter head</span>
						<select v-model="letterhead" class="form-select w-full sm:w-48" :disabled="!options">
							<option :value="NONE">No letter head</option>
							<option v-for="lh in options?.letter_heads || []" :key="lh.name" :value="lh.name">
								{{ lh.name }}{{ lh.is_default ? " (default)" : "" }}
							</option>
						</select>
					</label>
					<div class="flex w-full gap-2 sm:w-auto">
						<Button class="flex-1 sm:flex-none" icon-left="printer" label="Print" :disabled="!ready" @click="printNow" />
						<Button v-if="!trial" class="flex-1 sm:flex-none" variant="solid" icon-left="download" label="Download PDF"
							:loading="downloading" :disabled="!!errors.length" @click="download" />
						<Button icon="x" variant="ghost" label="Close" @click="close" />
					</div>
				</header>

				<!-- Preview -->
				<div ref="stage" class="relative flex-1 overflow-auto bg-gray-200 p-3 md:p-6">
					<div v-if="loading" class="absolute inset-0 z-10 flex items-center justify-center bg-gray-200/70">
						<LoadingIndicator class="h-6 w-6 text-gray-600" />
					</div>

					<div v-if="errors.length" class="mx-auto max-w-xl rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
						<p v-for="m in errors" :key="m">{{ m }}</p>
					</div>

					<!-- Print Designer formats only exist as PDF -->
					<template v-else-if="pdfUrl">
						<iframe :src="pdfUrl" class="h-full min-h-[70vh] w-full rounded bg-white" title="PDF preview" />
						<a :href="pdfUrl" target="_blank" class="mt-2 block text-center text-sm text-gray-700 underline md:hidden">
							Open the PDF if it doesn't show here
						</a>
					</template>

					<!-- HTML preview, scaled to fit narrow screens -->
					<div v-else class="mx-auto" :style="{ width: `${PAGE_WIDTH * scale}px`, height: `${pageHeight * scale}px` }">
						<iframe
							ref="frame"
							title="Print preview"
							class="origin-top-left rounded bg-white shadow"
							:style="{ width: `${PAGE_WIDTH}px`, height: `${pageHeight}px`, transform: `scale(${scale})` }"
							:srcdoc="srcdoc"
							@load="measure"
						/>
					</div>
				</div>
			</div>
		</div>
	</Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"
import { LoadingIndicator, call } from "frappe-ui"
import { api, errorMessages } from "@/utils/api"
import { downloadPdf, fetchPdf } from "@/utils/pdf"

// presetFormat: open on this format (the Proforma invoice button) without changing the remembered one
// trial: { method, args, note } renders an unsaved document through `method` instead (the trial payslip); no download
const props = defineProps({ open: Boolean, doctype: String, name: String, presetFormat: String, title: String,
	filePrefix: { type: String, default: "" }, trial: Object })
const emit = defineEmits(["update:open"])

const NONE = "__none__"
const PAGE_WIDTH = 860 // 8.3in A4 width plus gutter, in CSS px
const optionsCache = {}

const options = ref(null)
const format = ref(null)
const letterhead = ref(NONE)
const preview = ref(null)
const pdfUrl = ref(null)
const errors = ref([])
const loading = ref(false)
const downloading = ref(false)
const stage = ref(null)
const frame = ref(null)
const scale = ref(1)
const pageHeight = ref(1123)
let initialising = false

const selected = computed(() => ({
	print_format: format.value,
	letterhead: letterhead.value === NONE ? null : letterhead.value,
	no_letterhead: letterhead.value === NONE ? 1 : 0,
}))
const isPrintDesigner = computed(() => !!options.value?.formats.find((f) => f.name === format.value)?.print_designer)
const ready = computed(() => !loading.value && !errors.value.length && (pdfUrl.value || preview.value))

const storageKey = () => `erp-apps:sales:print:${props.doctype}`
function remember() {
	try {
		const keep = props.presetFormat ? recall()?.format ?? null : format.value
		localStorage.setItem(storageKey(), JSON.stringify({ format: keep, letterhead: letterhead.value }))
	} catch {}
}
function recall() {
	try {
		return JSON.parse(localStorage.getItem(storageKey()) || "null")
	} catch {
		return null
	}
}

// Mirrors desk's print view: format CSS + print bundle, body wrapped in .print-format, footer shown
const srcdoc = computed(() => {
	const p = preview.value
	if (!p) return ""
	const css = (p.css || []).map((href) => `<link rel="stylesheet" href="${location.origin}${href}">`).join("")
	return `<!DOCTYPE html><html><head><meta charset="utf-8"><base href="${location.origin}/">${css}
		<style>${p.style || ""}</style>
		<style>
			html, body { margin: 0; background: #fff; }
			.print-format { box-sizing: border-box; max-width: none; min-height: 11.69in; margin: 0; display: flex; flex-direction: column; }
			.print-format > .page-break { display: flex; flex-direction: column; flex: 1; }
			#footer-html { display: block !important; order: 1; margin-top: auto; padding-top: 24px; }
			@media print { .print-format { padding: 0; min-height: 0; } }
		</style></head>
		<body><div class="print-format print-format-preview">${p.html || ""}</div></body></html>`
})

async function loadOptions() {
	if (!optionsCache[props.doctype]) optionsCache[props.doctype] = await api("get_print_options", { doctype: props.doctype })
	options.value = optionsCache[props.doctype]
	const saved = recall()
	const formats = options.value.formats.map((f) => f.name)
	const heads = options.value.letter_heads.map((l) => l.name)
	format.value = formats.includes(props.presetFormat) ? props.presetFormat
		: formats.includes(saved?.format) ? saved.format : options.value.default_format
	letterhead.value =
		saved && (saved.letterhead === NONE || heads.includes(saved.letterhead))
			? saved.letterhead
			: options.value.default_letter_head || NONE
}

let requestId = 0
async function render() {
	if (!options.value || !format.value) return
	const id = ++requestId
	loading.value = true
	errors.value = []
	revokePdf()
	try {
		if (props.trial) {
			if (isPrintDesigner.value) throw new Error("Print Designer formats need a saved document. Pick another format.")
			const out = await call(props.trial.method, { ...props.trial.args, ...selected.value })
			if (id !== requestId) return
			preview.value = out
		} else if (isPrintDesigner.value) {
			const res = await fetchPdf(props.doctype, props.name, selected.value)
			if (id !== requestId) return
			if (res.error) errors.value = [res.error]
			else pdfUrl.value = URL.createObjectURL(res.blob)
			preview.value = null
		} else {
			const out = await api("get_print_preview", { doctype: props.doctype, name: props.name, ...selected.value })
			if (id !== requestId) return
			if (!out.html) errors.value = ["This print format has no template to preview."]
			preview.value = out
		}
	} catch (e) {
		if (id === requestId) errors.value = errorMessages(e)
	} finally {
		if (id === requestId) loading.value = false
	}
}

function measure() {
	const doc = frame.value?.contentDocument
	if (doc?.body) pageHeight.value = Math.max(1123, doc.documentElement.scrollHeight)
	fit()
}

function fit() {
	const width = stage.value?.clientWidth
	if (width) scale.value = Math.min(1, (width - 24) / PAGE_WIDTH)
}

function printNow() {
	if (pdfUrl.value) return window.open(pdfUrl.value, "_blank")
	frame.value?.contentWindow?.print()
}

async function download() {
	downloading.value = true
	try {
		await downloadPdf(props.doctype, props.name, selected.value, `${props.filePrefix}${props.name}.pdf`)
	} finally {
		downloading.value = false
	}
}

function revokePdf() {
	if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value)
	pdfUrl.value = null
}

function close() {
	emit("update:open", false)
}

function onKey(e) {
	if (e.key === "Escape") close()
}

watch(
	() => props.open,
	async (isOpen) => {
		if (!isOpen) {
			window.removeEventListener("keydown", onKey)
			window.removeEventListener("resize", fit)
			revokePdf()
			return
		}
		window.addEventListener("keydown", onKey)
		window.addEventListener("resize", fit)
		errors.value = []
		preview.value = null
		initialising = true
		try {
			await loadOptions()
		} catch (e) {
			errors.value = errorMessages(e)
			return
		} finally {
			await nextTick()
			initialising = false
		}
		fit()
		render()
	},
	{ immediate: true }, // also when mounted already open (v-if="printSlip" on the payroll run)
)

watch([format, letterhead], () => {
	if (!props.open || initialising) return
	remember()
	render()
})

onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKey)
	window.removeEventListener("resize", fit)
	revokePdf()
})
</script>
