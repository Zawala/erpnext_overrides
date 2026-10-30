"""The "Standard Payslip": a classic one-page payslip layout as a Salary Slip
print format, made the payslip employees get (Payroll Settings → Payslip format, so
/hrms downloads and payslip emails use it). Adds Employee → Bank Branch, which the
payslip prints. The layout lives in templates/print_formats/standard_payslip.html;
re-running refreshes it. Fresh installs get the same from after_install.
"""
from erp_overrides.payslip import install_standard_payslip


def execute():
	install_standard_payslip()
