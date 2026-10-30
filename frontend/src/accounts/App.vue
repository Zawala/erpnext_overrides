<template>
	<AccShell>
		<router-view />
	</AccShell>
	<Toasts />
</template>

<script setup>
import { Toasts } from "frappe-ui"
import AccShell from "./components/AccShell.vue"
</script>
