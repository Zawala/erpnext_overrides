<template>
	<footer class="border-t px-4 py-3 space-y-2">
		<textarea v-model="comment" rows="1" class="form-textarea w-full text-sm"
			:placeholder="rejectNeedsComment ? 'Comment (needed to decline)' : 'Comment (optional)'" aria-label="Comment" />
		<p v-if="needComment" class="text-xs text-red-600">Say why, so they can fix it and send it again.</p>
		<div class="flex gap-2">
			<Button class="flex-1" theme="red" variant="subtle" :label="rejectLabel" :loading="busy && pending === 'Rejected'"
				:disabled="busy" @click="go('Rejected')" />
			<Button class="flex-1" variant="solid" :label="approveLabel" :loading="busy && pending === 'Approved'"
				:disabled="busy" @click="go('Approved')" />
		</div>
	</footer>
</template>

<script setup>
import { ref } from "vue"

const props = defineProps({
	busy: Boolean,
	approveLabel: { type: String, default: "Approve" },
	rejectLabel: { type: String, default: "Reject" },
	rejectNeedsComment: Boolean,
})
const emit = defineEmits(["decide"])
const comment = ref("")
const pending = ref(null)
const needComment = ref(false)

function go(status) {
	needComment.value = status === "Rejected" && props.rejectNeedsComment && !comment.value.trim()
	if (needComment.value) return
	pending.value = status
	emit("decide", status, comment.value.trim() || undefined)
}
</script>
