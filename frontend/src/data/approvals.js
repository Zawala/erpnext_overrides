import { ref } from "vue"
import { boot } from "@/boot"
import { api } from "@/utils/api"

export const approvals = ref([])
export const approvalCount = ref(0)

export async function loadApprovals() {
	if (!boot.is_approver) return []
	approvals.value = await api("get_approvals")
	approvalCount.value = approvals.value.length
	return approvals.value
}
