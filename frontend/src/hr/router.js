import { createRouter, createWebHistory } from "vue-router"
import { boot } from "@/boot"

// Approver-only users get Home, Inbox, Who's off and their team's balances; everything else is HR's.
// Other employees get Who's off and their reviews (boot.employee_only).
const hrOnly = { hrOnly: true }

const routes = [
	{ path: "/", name: "Home", component: () => import("./pages/Home.vue") },
	{ path: "/calendar", name: "Calendar", component: () => import("./pages/Calendar.vue") },
	// bi-weekly reviews (erp_overrides.reviews): HR's dashboard, forms and schedules; everyone's own
	{ path: "/my-reviews", name: "MyReviews", component: () => import("./pages/MyReviews.vue") },
	{ path: "/reviews", name: "Reviews", component: () => import("./pages/Reviews.vue"), meta: hrOnly },
	{ path: "/reviews/:name", name: "Review", component: () => import("./pages/ReviewPage.vue"), props: true },
	{ path: "/review-forms/:name", name: "ReviewForm", component: () => import("./pages/ReviewFormEditor.vue"), props: true, meta: hrOnly },
	{ path: "/review-schedules/:name", name: "ReviewSchedule", component: () => import("./pages/ReviewScheduleEditor.vue"), props: true, meta: hrOnly },
	{ path: "/inbox", name: "Inbox", component: () => import("./pages/Inbox.vue") },
	{ path: "/balances", name: "Balances", component: () => import("./pages/Balances.vue") },
	{ path: "/leave", name: "Leave", component: () => import("./pages/Leave.vue"), meta: hrOnly },
	{ path: "/expenses", name: "Expenses", component: () => import("./pages/Expenses.vue"), meta: hrOnly },
	{ path: "/attendance", name: "Attendance", component: () => import("./pages/Attendance.vue"), meta: hrOnly },
	{ path: "/payroll", name: "Payroll", component: () => import("./pages/Payroll.vue"), meta: hrOnly },
	{ path: "/salaries", name: "Salaries", component: () => import("./pages/Salaries.vue"), meta: hrOnly },
	{ path: "/pay-setup", name: "PaySetup", component: () => import("./pages/PaySetup.vue"), meta: hrOnly },
	{ path: "/pay-report", name: "PayReport", component: () => import("./pages/PayReport.vue"), meta: hrOnly },
	{ path: "/payroll/:name", name: "PayrollRun", component: () => import("./pages/PayrollRun.vue"), props: true, meta: hrOnly },
	{ path: "/people", name: "People", component: () => import("./pages/People.vue"), meta: hrOnly },
	{ path: "/people/:name", name: "Employee", component: () => import("./pages/EmployeePage.vue"), props: true, meta: hrOnly },
	{ path: "/people/:employee/:kind", name: "Lifecycle", component: () => import("./pages/LifecycleForm.vue"), props: true, meta: hrOnly },
	{ path: "/records/:slug", name: "Records", component: () => import("./pages/RecordList.vue"), props: true, meta: hrOnly },
	{ path: "/records/:slug/:name", name: "Record", component: () => import("./pages/RecordPage.vue"), props: true, meta: hrOnly },
	{ path: "/reports", name: "Reports", component: () => import("./pages/Reports.vue"), meta: hrOnly },
	{ path: "/settings", name: "Settings", component: () => import("./pages/Settings.vue"), meta: { managerOnly: true } },
	{ path: "/:pathMatch(.*)*", redirect: "/" },
]

const router = createRouter({ history: createWebHistory("/hrms-admin"), routes })

router.beforeEach((to) => {
	// an employee who is neither HR nor an approver only has Who's off
	if (boot.employee_only) return ["Calendar", "MyReviews", "Review"].includes(to.name) ? true : { name: "Calendar" }
	if (to.name === "Reviews" && !boot.is_hr) return { name: "MyReviews" }
	return (to.meta.hrOnly && !boot.is_hr) || (to.meta.managerOnly && !boot.is_settings_manager) ? { name: "Home" } : true
})

export default router
