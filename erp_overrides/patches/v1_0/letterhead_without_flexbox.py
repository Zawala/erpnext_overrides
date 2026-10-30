# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt

"""Rewrite flexbox in Letter Head HTML so wkhtmltopdf can lay it out.

wkhtmltopdf renders with a 2012-era WebKit that has no flexbox. A letter head
that lays out a row of logos with `display: flex; flex-wrap: wrap` shows as
wrapped rows in a browser, but wkhtmltopdf stacks them one per line: the footer
grows taller than the page and every PDF comes out blank.

A wrapping flex container becomes `text-align` + `inline-block` children, and a
non-wrapping flex box centring its content becomes an inline-block with
`line-height` centring. Browsers render the result the same way.
"""

import re

import frappe
from bs4 import BeautifulSoup

HTML_FIELDS = ("content", "footer")
JUSTIFY_TO_ALIGN = {"center": "center", "flex-start": "left", "start": "left", "flex-end": "right", "end": "right"}


def execute():
	run()


def run(dry_run=False):
	changed = []
	for lh in frappe.get_all("Letter Head", fields=["name", *HTML_FIELDS]):
		updates = {}
		for field in HTML_FIELDS:
			html = lh.get(field) or ""
			if "flex" not in html:
				continue
			new_html = without_flexbox(html)
			if new_html != html:
				updates[field] = new_html
		if updates:
			changed.append(lh.name)
			print(f"Letter Head {lh.name}: rewrote flexbox in {', '.join(updates)}")
			if not dry_run:
				frappe.db.set_value("Letter Head", lh.name, updates, update_modified=False)
	return changed


def without_flexbox(html):
	soup = BeautifulSoup(html, "html.parser")
	touched = False
	for el in soup.find_all(style=re.compile(r"display\s*:\s*(inline-)?flex", re.I)):
		style = parse_style(el["style"])
		wraps = style.get("flex-wrap", "nowrap") != "nowrap" or style.get("flex-direction", "row").startswith("column")
		justify = JUSTIFY_TO_ALIGN.get(style.get("justify-content", ""), None)
		centred_vertically = style.get("align-items") == "center"

		for prop in ("display", "flex-wrap", "flex-direction", "flex-flow", "justify-content", "align-items", "gap"):
			style.pop(prop, None)

		if wraps:
			# container: children flow as inline-blocks and wrap like text
			if justify:
				style["text-align"] = justify
			for child in el.find_all(recursive=False):
				child_style = parse_style(child.get("style", ""))
				if "display" not in child_style or "flex" in child_style["display"]:
					child_style.setdefault("display", "inline-block")
					child_style.setdefault("vertical-align", "middle")
					child_style.setdefault("margin", "3px")
					child["style"] = format_style(child_style)
		else:
			# single box centring its content
			style["display"] = "inline-block"
			style.setdefault("vertical-align", "middle")
			if justify:
				style["text-align"] = justify
			if centred_vertically and style.get("height"):
				style["line-height"] = style["height"]
				for img in el.find_all("img", recursive=False):
					img_style = parse_style(img.get("style", ""))
					img_style["vertical-align"] = "middle"
					img["style"] = format_style(img_style)

		el["style"] = format_style(style)
		touched = True

	return str(soup) if touched else html


def parse_style(style):
	out = {}
	for part in style.split(";"):
		if ":" in part:
			key, value = part.split(":", 1)
			out[key.strip().lower()] = value.strip()
	return out


def format_style(style):
	return "; ".join(f"{k}: {v}" for k, v in style.items()) + ";"
