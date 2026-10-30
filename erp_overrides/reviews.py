# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Bi-weekly reviews: a self check-in by the employee, then their manager's ratings and comments.

HR sets up a Review Form (the questions) and a Review Schedule (who, how often, the form).
Periods run back to back from the schedule's first period; the day after a period ends a
Review opens for each person and stays open for the schedule's window. Reminders go by
email and as bell notifications (scheduler, below).

When the manager completes a review and the employee has an Appraisal in an In Progress
Appraisal Cycle covering the period, the manager's ratings are posted on it as Employee
Performance Feedback, so they count in the appraisal score (HRMS averages the feedback).
"""
import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_url, getdate, now_datetime, nowdate, strip_html

STEPS = {"Every 2 weeks": (14, 0), "Weekly": (7, 0), "Monthly": (0, 1)}
REMIND_DAYS_BEFORE = 2
RATING_MAX = 5


def review_url(name):
	return get_url(f"/hrms-admin/reviews/{name}")


# ── Periods ──────────────────────────────────────────────────────────────────

def period(schedule, k):
	"""(start, end) of the schedule's k-th period (k from 0)."""
	days, months = STEPS.get(schedule.frequency, STEPS["Every 2 weeks"])
	first = getdate(schedule.first_period_start)
	if months:
		start = getdate(add_months(first, k * months))
		return start, add_days(add_months(start, months), -1)
	start = add_days(first, k * days)
	return getdate(start), getdate(add_days(start, days - 1))


def window(schedule, start, end):
	"""(opens_on, due_on): open the day after the period, for window_days days."""
	opens = getdate(add_days(end, 1))
	return opens, getdate(add_days(opens, max(cint(schedule.window_days), 1) - 1))


def periods_open_on(schedule, day):
	"""Periods whose review window includes `day` (normally one)."""
	day = getdate(day)
	out, k = [], 0
	while True:
		start, end = period(schedule, k)
		opens, due = window(schedule, start, end)
		if opens > day:
			return out
		if due >= day:
			out.append((start, end, opens, due))
		k += 1
		if k > 2000:  # a first period decades back; never loop forever
			return out


def next_windows(schedule, count=3, after=None):
	after = getdate(after or nowdate())
	out, k = [], 0
	while len(out) < count and k < 2000:
		start, end = period(schedule, k)
		opens, due = window(schedule, start, end)
		if due >= after:
			out.append(dict(period_start=start, period_end=end, opens_on=opens, due_on=due))
		k += 1
	return out


# ── Who ──────────────────────────────────────────────────────────────────────

def manager_of(employee):
	"""The Employee who reviews `employee`: Reports To, else the leave approver's employee."""
	row = frappe.db.get_value("Employee", employee, ["reports_to", "leave_approver"], as_dict=True)
	if not row:
		return None
	if row.reports_to and frappe.db.get_value("Employee", row.reports_to, "status") == "Active":
		return row.reports_to
	if row.leave_approver:
		return frappe.db.get_value("Employee", {"user_id": row.leave_approver, "status": "Active"}, "name")
	return None


def people(schedule):
	"""Active employees the schedule covers."""
	if schedule.employees:
		names = [r.employee for r in schedule.employees]
		return frappe.get_all("Employee", filters={"name": ["in", names], "status": "Active"}, pluck="name")
	filters = {"status": "Active", "company": schedule.company}
	for f in ("department", "branch", "designation"):
		if schedule.get(f):
			filters[f] = schedule.get(f)
	return frappe.get_all("Employee", filters=filters, pluck="name", order_by="employee_name asc")


# ── Opening, reminding, overdue (scheduler) ──────────────────────────────────

def open_reviews(day=None):
	"""Open the reviews whose window includes `day` and don't exist yet. Safe to run repeatedly."""
	day = getdate(day or nowdate())
	opened = []
	for name in frappe.get_all("Review Schedule", filters={"active": 1}, pluck="name"):
		schedule = frappe.get_doc("Review Schedule", name)
		form = frappe.get_cached_doc("Review Form", schedule.review_form)
		skipped = []
		for start, end, opens, due in periods_open_on(schedule, day):
			for emp in people(schedule):
				if frappe.db.exists("Review", {"schedule": name, "employee": emp, "period_start": start}):
					continue
				manager = manager_of(emp)
				if not manager:
					skipped.append(frappe.db.get_value("Employee", emp, "employee_name") or emp)
					continue
				opened.append(_create(schedule, form, emp, manager, start, end, opens, due))
		note = ", ".join(sorted(set(skipped)))
		if note != (schedule.skipped or ""):
			frappe.db.set_value("Review Schedule", name, "skipped", note, update_modified=False)
	for review in opened:
		_announce(review)
	return [r.name for r in opened]


def _create(schedule, form, employee, manager, start, end, opens, due):
	review = frappe.get_doc(dict(
		doctype="Review", schedule=schedule.name, review_form=form.name, employee=employee,
		employee_user=frappe.db.get_value("Employee", employee, "user_id"),
		manager=manager, manager_user=frappe.db.get_value("Employee", manager, "user_id"),
		period_start=start, period_end=end, opens_on=opens, due_on=due, status="Open",
		answers=[dict(question=q.label, help=q.help, kind=q.kind, options=q.options, answered_by=q.answered_by,
		              required=q.required, criteria=q.criteria) for q in form.questions],
	))
	review.insert(ignore_permissions=True)
	return review


def _fmt(d):
	return frappe.utils.formatdate(d, "d MMM")


def _notify(user, review, subject, lines):
	"""Email + bell notification, both linking to the review in the HR app."""
	if not user:
		return
	url = review_url(review.name)
	body = "".join(f"<p>{line}</p>" for line in lines) + \
		f'<p><a href="{url}" style="display:inline-block;padding:8px 14px;background:#111827;color:#fff;' \
		f'border-radius:6px;text-decoration:none">Open the review</a></p>'
	frappe.sendmail(recipients=[user], subject=subject, message=body, reference_doctype="Review",
	                reference_name=review.name)
	frappe.get_doc(dict(doctype="Notification Log", for_user=user, type="Alert", document_type="Review",
	                    document_name=review.name, subject=subject, email_content=body, link=url)
	               ).insert(ignore_permissions=True)


def _announce(review):
	span = f"{_fmt(review.period_start)} – {_fmt(review.period_end)}"
	due = frappe.utils.formatdate(review.due_on, "EEEE d MMMM")
	_notify(review.employee_user, review, _("Your check-in for {0} is open").format(span),
	        [_("Your review for {0} is open. Fill in your part by {1}; {2} then adds their comments.")
	         .format(span, due, review.manager_name or _("your manager"))])
	_notify(review.manager_user, review, _("Review {0}: {1}").format(span, review.employee_name),
	        [_("{0}'s review for {1} is open. Once they have filled in their part, add yours by {2}.")
	         .format(review.employee_name, span, due)])


def remind(day=None):
	"""Two days before the due date, nudge whoever's part isn't done."""
	day = getdate(day or nowdate())
	target = add_days(day, REMIND_DAYS_BEFORE)
	sent = []
	for name in frappe.get_all("Review", filters={"due_on": target, "status": ["!=", "Completed"]}, pluck="name"):
		review = frappe.get_doc("Review", name)
		due = frappe.utils.formatdate(review.due_on, "EEEE d MMMM")
		if review.status == "Open":
			_notify(review.employee_user, review, _("Reminder: your check-in is due {0}").format(due),
			        [_("Your review for {0} – {1} is due on {2}.").format(_fmt(review.period_start), _fmt(review.period_end), due)])
			sent.append((name, review.employee_user))
		else:
			_notify(review.manager_user, review, _("Reminder: {0}'s review is due {1}").format(review.employee_name, due),
			        [_("{0} has done their part. Add your ratings and comments by {1}.").format(review.employee_name, due)])
			sent.append((name, review.manager_user))
	return sent


def mark_overdue(day=None):
	day = getdate(day or nowdate())
	names = frappe.get_all("Review", filters={"due_on": ["<", day], "status": ["!=", "Completed"], "overdue": 0}, pluck="name")
	for name in names:
		frappe.db.set_value("Review", name, "overdue", 1, update_modified=False)
	return names


def daily():
	open_reviews()
	remind()
	mark_overdue()


def weekly_overdue_summary():
	"""To HR: reviews past their due date, by manager."""
	from erp_overrides.tender_digest import _esc, _section

	rows = frappe.get_all("Review", filters={"overdue": 1, "status": ["!=", "Completed"]},
	                      fields=["name", "employee_name", "manager_name", "period_start", "period_end", "due_on",
	                              "status", "schedule"], order_by="manager_name asc, due_on asc")
	if not rows:
		return None
	by_schedule = {}
	for r in rows:
		by_schedule.setdefault(r.schedule, []).append(r)
	sent = []
	for schedule, items in by_schedule.items():
		recipients = _hr_recipients(schedule)
		if not recipients:
			continue
		table = [[_esc(r.manager_name or "—"), f'<a href="{review_url(r.name)}">{_esc(r.employee_name)}</a>',
		          f"{_fmt(r.period_start)} – {_fmt(r.period_end)}", _fmt(r.due_on),
		          _("Waiting for the employee") if r.status == "Open" else _("Waiting for the manager")] for r in items]
		html = (f"<p>{_('{0} reviews in {1} are past their due date.').format(len(items), _esc(schedule))}</p>"
		        + _section(_("By manager"), [_("Manager"), _("Employee"), _("Period"), _("Due"), _("Waiting on")], table)
		        + f"<p>{_('Reviews stay open after the due date; a manager or employee can still complete them.')}</p>")
		frappe.sendmail(recipients=recipients, subject=_("Overdue reviews: {0}").format(len(items)), message=html)
		sent.append((schedule, recipients, len(items)))
	return sent


def _hr_recipients(schedule):
	listed = frappe.db.get_value("Review Schedule", schedule, "hr_recipients") or ""
	emails = [e.strip() for e in listed.replace("\n", ",").split(",") if e.strip()]
	if emails:
		return emails
	return frappe.get_all("Has Role", filters={"role": "HR Manager", "parenttype": "User",
	                                           "parent": ["not in", ["Administrator", "Guest"]]}, pluck="parent", distinct=True)


# ── Completing and the appraisal ─────────────────────────────────────────────

def ratings(review, part="manager_answer"):
	"""(criteria, rating 1–5) for the Rating answers of one side."""
	out = []
	for a in review.answers:
		if a.kind == "Rating" and a.get(part) not in (None, ""):
			out.append((a.criteria, flt(a.get(part))))
	return out


def post_to_appraisal(review):
	"""Post the manager's ratings as Employee Performance Feedback on the employee's appraisal in an
	In Progress cycle covering the period. Returns (appraisal, feedback) or (None, reason)."""
	cycle = frappe.qb.DocType("Appraisal Cycle")
	appraisal = frappe.qb.DocType("Appraisal")
	row = (frappe.qb.from_(appraisal).join(cycle).on(appraisal.appraisal_cycle == cycle.name)
	       .select(appraisal.name, appraisal.appraisal_template)
	       .where((appraisal.employee == review.employee) & (appraisal.docstatus < 2) & (cycle.status == "In Progress")
	              & (cycle.start_date <= review.period_end) & (cycle.end_date >= review.period_start))
	       .limit(1)).run(as_dict=True)
	if not row:
		return None, _("No appraisal open for this period, so nothing was added to an appraisal.")
	row = row[0]
	given = ratings(review)
	if not given:
		return None, _("No ratings from the manager, so nothing was added to the appraisal.")
	by_criteria = {c: r for c, r in given if c}
	average = sum(r for _c, r in given) / len(given)
	template = frappe.get_cached_doc("Appraisal Template", row.appraisal_template) if row.appraisal_template else None
	criteria = [(c.criteria, c.per_weightage) for c in (template.rating_criteria if template else [])]
	if not criteria:
		return None, _("The appraisal's template has no rating criteria, so nothing was added to it.")
	comments = [f"<b>{frappe.utils.escape_html(a.question)}</b>: {frappe.utils.escape_html(a.manager_answer)}"
	            for a in review.answers if a.kind != "Rating" and a.manager_answer]
	if review.manager_comments:
		comments.append(frappe.utils.escape_html(review.manager_comments))
	feedback = frappe.get_doc(dict(
		doctype="Employee Performance Feedback", appraisal=row.name, employee=review.employee, reviewer=review.manager,
		added_on=now_datetime(),
		feedback=(_("Review {0} ({1} – {2})").format(review.name, _fmt(review.period_start), _fmt(review.period_end))
		          + "<br>" + "<br>".join(comments)),
		feedback_ratings=[dict(criteria=c, per_weightage=w, rating=flt(by_criteria.get(c, average)) / RATING_MAX)
		                  for c, w in criteria],
	))
	feedback.insert(ignore_permissions=True)
	feedback.submit()
	return row.name, feedback.name
