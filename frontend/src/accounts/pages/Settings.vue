<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Settings" subtitle="Petty cash, reconciliation, invoices and exchange rates — managers only; every change is recorded" />
		<SettingsPage app="accounts" />
	</div>
</template>

<script setup>
import PageHeader from "@/hr/components/PageHeader.vue"
import SettingsPage from "@/components/SettingsPage.vue"
</script>
