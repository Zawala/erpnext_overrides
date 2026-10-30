<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Settings" subtitle="Lead-to-order rules: approval limits, selling and stock defaults — managers only; every change is recorded" />
		<SettingsPage app="sales" />
	</div>
</template>

<script setup>
import PageHeader from "@/hr/components/PageHeader.vue"
import SettingsPage from "@/components/SettingsPage.vue"
</script>
