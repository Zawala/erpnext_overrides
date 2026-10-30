<template>
	<AppShell>
		<router-view />
	</AppShell>
	<Toasts />
</template>

<script setup>
import { Toasts } from "frappe-ui"
import AppShell from "@/components/AppShell.vue"
</script>
