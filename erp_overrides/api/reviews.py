# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Bi-weekly reviews in the HR app (erp_overrides.reviews).

HR edits Review Forms and Review Schedules as documents (they have desk rights on them).
Employees and managers have no rights on Review: everything they do goes through here,
and every call checks that the review is theirs.
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate

from erp_overrides import reviews
from erp_overrides.api.hr import is_hr

LIST_FIELDS = ["name", "employee", "employee_name", "department", "manager", "manager_name", "period_start", "period_end",
               "opens_on", "due_on", "status", "overdue", "schedule", "completed_on", "appraisal", "feedback"]


def me(user=None):
	return frappe.db.get_value("Employee", {"user_id": user or frappe.session.user, "status": "Active"}, "name")


def has_reports(user=None):
	emp = me(user)
	return bool(emp and (frappe.db.exists("Employee", {"reports_to": emp, "status": "Active"})
	                     or frappe.db.exists("Review", {"manager": emp})))


def has_reviews(user=None):
	emp = me(user)
	return bool(emp and (frappe.db.exists("Review", {"employee": emp}) or frappe.db.exists("Review", {"manager": emp})))


def _require_hr():
	if not is_hr():
		frappe.throw(_("Only HR can do this."), frappe.PermissionError)


def _role(review):
	"""'hr', 'employee', 'manager' (or both of the last two never: no self-review) for the caller."""
	emp = me()
	if emp and review.manager == emp:
		return "manager"
	if emp and review.employee == emp:
		return "employee"
	if is_hr():
		return "hr"
	frappe.throw(_("This review isn't yours."), frappe.PermissionError)


def _manager_may_edit(review):
	# once the employee is done, or after the due date if they never were
	return review.status == "Self done" or (review.status == "Open" and getdate(review.due_on) < getdate(nowdate()))


# ── Everyone ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def my_reviews():
	"""The caller's own reviews, and the ones they review as a manager."""
	emp = me()
	if not emp:
		return dict(me=None, mine=[], team=[])
	return dict(
		me=emp,
		mine=frappe.get_all("Review", filters={"employee": emp}, fields=LIST_FIELDS, order_by="period_start desc", limit=30),
		# what still needs doing first, then by due date
		team=sorted(frappe.get_all("Review", filters={"manager": emp}, fields=LIST_FIELDS, order_by="due_on desc", limit=200),
		            key=lambda r: (r.status == "Completed", str(r.due_on), r.employee_name or "")),
	)


@frappe.whitelist()
def get_review(name: str):
	review = frappe.get_doc("Review", name)
	role = _role(review)
	out = review.as_dict()
	out.role = role
	out.can_edit_self = role == "employee" and review.status == "Open"
	out.can_edit_manager = role == "manager" and review.status != "Completed" and _manager_may_edit(review)
	out.intro = frappe.db.get_value("Review Form", review.review_form, "intro")
	if role == "employee" and review.status != "Completed":
		# the manager's part stays private until they complete it
		for a in out.answers:
			a.manager_answer = None
		out.manager_comments = None
	return out


@frappe.whitelist(methods=["POST"])
def save_review(name: str, answers: dict | str | None = None, manager_comments: str | None = None, done: int = 0):
	"""Save the caller's part; with `done`, check it is complete and move the review on."""
	review = frappe.get_doc("Review", name)
	role = _role(review)
	answers = frappe.parse_json(answers) if isinstance(answers, str) else (answers or {})
	if role == "employee":
		if review.status != "Open":
			frappe.throw(_("You've already sent your part of this review."))
		mine, field = ("Employee", "Both"), "employee_answer"
	elif role == "manager":
		if review.status == "Completed":
			frappe.throw(_("This review is completed. Ask HR to reopen it."))
		if not _manager_may_edit(review):
			frappe.throw(_("{0} hasn't sent their part yet. You can add yours once they have, or after the due date.")
			             .format(review.employee_name))
		mine, field = ("Manager", "Both"), "manager_answer"
	else:
		frappe.throw(_("Only the employee and their manager fill in a review."), frappe.PermissionError)

	for row in review.answers:
		if row.answered_by not in mine or row.name not in answers:
			continue
		value = answers[row.name]
		value = "" if value is None else str(value).strip()
		if value and row.kind == "Rating" and (not value.isdigit() or not 1 <= int(value) <= reviews.RATING_MAX):
			frappe.throw(_("{0}: pick a rating from 1 to {1}.").format(row.question, reviews.RATING_MAX))
		row.set(field, value)
	if role == "manager" and manager_comments is not None:
		review.manager_comments = manager_comments

	if cint(done):
		missing = [r.question for r in review.answers if r.answered_by in mine and r.required and not r.get(field)]
		if missing:
			frappe.throw(_("Answer these first: {0}").format(", ".join(missing)))
		if role == "employee":
			review.status, review.self_done_on = "Self done", now_datetime()
		else:
			review.status, review.completed_on = "Completed", now_datetime()
	review.save(ignore_permissions=True)

	if cint(done) and role == "employee":
		reviews._notify(review.manager_user, review, _("{0} has done their check-in").format(review.employee_name),
		                [_("{0} has filled in their part of the review for {1} – {2}. Add your ratings and comments by {3}.")
		                 .format(review.employee_name, reviews._fmt(review.period_start), reviews._fmt(review.period_end),
		                         frappe.utils.formatdate(review.due_on, "EEEE d MMMM"))])
	if cint(done) and role == "manager":
		appraisal, result = reviews.post_to_appraisal(review)
		review.db_set(dict(appraisal=appraisal, feedback=result if appraisal else None,
		                   rollup_note=None if appraisal else result), update_modified=False)
		reviews._notify(review.employee_user, review, _("Your review is complete"),
		                [_("{0} has completed your review for {1} – {2}.").format(
		                    review.manager_name, reviews._fmt(review.period_start), reviews._fmt(review.period_end))])
	return get_review(name)


# ── HR ───────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_reviews(status: str | None = None, schedule: str | None = None, manager: str | None = None,
                overdue: int | None = None, since: str | None = None):
	"""All reviews (newest windows first) and this window's progress by manager."""
	_require_hr()
	filters = {}
	if status:
		filters["status"] = status
	if schedule:
		filters["schedule"] = schedule
	if manager:
		filters["manager"] = manager
	if cint(overdue):
		filters["overdue"] = 1
	filters["opens_on"] = [">=", getdate(since) if since else add_days(nowdate(), -45)]
	rows = frappe.get_all("Review", filters=filters, fields=LIST_FIELDS, order_by="opens_on desc, employee_name asc", limit=500)
	by_manager = {}
	for r in rows:
		m = by_manager.setdefault(r.manager or "", dict(manager=r.manager, manager_name=r.manager_name or "—", open=0,
		                                                 self_done=0, completed=0, overdue=0))
		m[{"Open": "open", "Self done": "self_done", "Completed": "completed"}[r.status]] += 1
		m["overdue"] += cint(r.overdue and r.status != "Completed")
	totals = {k: sum(m[k] for m in by_manager.values()) for k in ("open", "self_done", "completed", "overdue")}
	return dict(rows=rows, by_manager=sorted(by_manager.values(), key=lambda m: m["manager_name"]), totals=totals,
	            schedules=frappe.get_all("Review Schedule", fields=["name", "active", "frequency", "review_form", "skipped"]),
	            forms=frappe.get_all("Review Form", fields=["name", "active", "modified"], order_by="name asc"))


@frappe.whitelist()
def preview_schedule(doc: dict | str):
	"""The next windows of an (unsaved) schedule, who each covers, and who has no manager."""
	_require_hr()
	schedule = frappe.get_doc(frappe.parse_json(doc) if isinstance(doc, str) else doc)
	if not schedule.first_period_start or not schedule.company:
		return dict(windows=[], people=[], no_manager=[])
	names = reviews.people(schedule)
	rows = frappe.get_all("Employee", filters={"name": ["in", names or [""]]}, fields=["name", "employee_name", "department"],
	                      order_by="employee_name asc")
	no_manager = []
	for r in rows:
		r.manager = reviews.manager_of(r.name)
		r.manager_name = r.manager and frappe.db.get_value("Employee", r.manager, "employee_name")
		if not r.manager:
			no_manager.append(r.employee_name)
	return dict(windows=reviews.next_windows(schedule), people=rows, no_manager=no_manager)


@frappe.whitelist(methods=["POST"])
def open_now():
	"""Open any review whose window has started (the daily job does this at 06:00)."""
	_require_hr()
	return reviews.open_reviews()


@frappe.whitelist(methods=["POST"])
def reopen(name: str):
	"""Back to the manager (Self done) or the employee (Open); an appraisal feedback it posted is cancelled."""
	_require_hr()
	review = frappe.get_doc("Review", name)
	if review.feedback and frappe.db.get_value("Employee Performance Feedback", review.feedback, "docstatus") == 1:
		frappe.get_doc("Employee Performance Feedback", review.feedback).cancel()
	review.status = "Self done" if review.self_done_on else "Open"
	review.completed_on = review.feedback = review.appraisal = review.rollup_note = None
	review.save(ignore_permissions=True)
	return get_review(name)


@frappe.whitelist()
def get_criteria():
	"""Employee Feedback Criteria, for the form builder's appraisal-criterion picker."""
	_require_hr()
	return frappe.get_all("Employee Feedback Criteria", pluck="name", order_by="name asc")
