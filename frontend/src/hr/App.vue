<template>
	<HrShell>
		<router-view />
	</HrShell>
	<Toasts />
</template>

<script setup>
import { Toasts } from "frappe-ui"
import HrShell from "./components/HrShell.vue"
</script>
