<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Settings" subtitle="Leave, attendance and payroll rules — managers only; every change is recorded" />
		<SettingsPage app="hr" />
	</div>
</template>

<script setup>
import PageHeader from "@/hr/components/PageHeader.vue"
import SettingsPage from "@/components/SettingsPage.vue"
</script>
