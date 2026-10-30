<template>
	<div class="h-full overflow-y-auto">
		<PageHeader title="Who's off" subtitle="Leave across the company, approved and waiting, with holidays" />
		<div class="mx-auto w-full max-w-[1600px] p-4 lg:p-6">
			<LeaveCalendar />
		</div>
	</div>
</template>

<script setup>
import PageHeader from "../components/PageHeader.vue"
import LeaveCalendar from "../components/LeaveCalendar.vue"
</script>
