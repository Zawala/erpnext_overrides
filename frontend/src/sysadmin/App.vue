<template>
	<AdminShell>
		<router-view />
	</AdminShell>
	<Toasts />
</template>

<script setup>
import { Toasts } from "frappe-ui"
import AdminShell from "./components/AdminShell.vue"
</script>
