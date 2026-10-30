import { ref } from "vue"

// Pending approvals across leave, claims and attendance requests — the sidebar badge
export const inboxCount = ref(0)
export const setInboxCount = (pending) =>
	(inboxCount.value = (pending?.leave || 0) + (pending?.expense || 0) + (pending?.attendance || 0))
