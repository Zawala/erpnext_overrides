<template>
	<Badge v-if="status" :theme="statusTheme(status)" :size="size" variant="subtle" :label="status" />
</template>

<script setup>
import { Badge } from "frappe-ui"
import { statusTheme } from "@/utils/format"

defineProps({ status: String, size: { type: String, default: "md" } })
</script>
