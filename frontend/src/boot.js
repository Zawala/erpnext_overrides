import { reactive } from "vue"

// filled from window.frappe.boot (www/sales.py) before the app mounts
export const boot = reactive({})

export const hasRole = (...roles) => roles.some((r) => (boot.roles || []).includes(r))
