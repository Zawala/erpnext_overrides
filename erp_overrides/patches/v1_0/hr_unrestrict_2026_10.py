"""Lift the own-record Employee User Permission from everyone with an HR role
(erp_overrides.hr_access): it made the HR app refuse payroll runs naming anyone else."""
from erp_overrides.hr_access import hr_users, lift


def execute():
	for user in hr_users():
		lift(user)
