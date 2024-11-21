import frappe
from frappe import _
from erpnext.accounts.general_ledger import (
	make_acc_dimensions_offsetting_entry,
	validate_accounting_period,
	validate_disabled_accounts,
	process_gl_map,
	validate_cwip_accounts,
	process_debit_credit_difference,
	check_freezing_date,
	validate_against_pcv,
	make_reverse_gl_entries,
	validate_allowed_dimensions
	
)
from erpnext.accounts.utils import create_payment_ledger_entry
from erpnext.accounts.doctype.budget.budget import validate_expense_against_budget
from erpnext.accounts.doctype.accounting_dimension_filter.accounting_dimension_filter import (
	get_dimension_filter_map,
)

def custom_gl_make_gl_entries(
	gl_map,
	cancel=False,
	adv_adj=False,
	merge_entries=True,
	update_outstanding="Yes",
	from_repost=False,
	clearing_date = None
):
	if gl_map:
		if not cancel:
			make_acc_dimensions_offsetting_entry(gl_map)
			validate_accounting_period(gl_map)
			validate_disabled_accounts(gl_map)
			gl_map = process_gl_map(gl_map, merge_entries)
			if gl_map and len(gl_map) > 1:
				create_payment_ledger_entry(
					gl_map,
					cancel=0,
					adv_adj=adv_adj,
					update_outstanding=update_outstanding,
					from_repost=from_repost,
				)
				custom_save_entries(gl_map, adv_adj, update_outstanding, from_repost,clearing_date=clearing_date)
			# Post GL Map proccess there may no be any GL Entries
			elif gl_map:
				frappe.throw(
					_(
						"Incorrect number of General Ledger Entries found. You might have selected a wrong Account in the transaction."
					)
				)
		else:
			make_reverse_gl_entries(gl_map, adv_adj=adv_adj, update_outstanding=update_outstanding)

def custom_save_entries(gl_map, adv_adj, update_outstanding, from_repost=False,clearing_date=None):
	if not from_repost:
		validate_cwip_accounts(gl_map)

	process_debit_credit_difference(gl_map)

	dimension_filter_map = get_dimension_filter_map()
	if gl_map:
		check_freezing_date(gl_map[0]["posting_date"], adv_adj)
		is_opening = any(d.get("is_opening") == "Yes" for d in gl_map)
		if gl_map[0]["voucher_type"] != "Period Closing Voucher":
			validate_against_pcv(is_opening, gl_map[0]["posting_date"], gl_map[0]["company"])
	# frappe.throw(f"{gl_map}")
	for entry in gl_map:
		validate_allowed_dimensions(entry, dimension_filter_map)
		custom_make_entry(entry, adv_adj, update_outstanding, from_repost,clearing_date)


def custom_make_entry(args, adv_adj, update_outstanding, from_repost=False,clearing_date=None):
	gle = frappe.new_doc("GL Entry")
	
	if args.is_cancelled == 0  and clearing_date:
		gle.posting_date=clearing_date
	if clearing_date:
		gle.custom_reconciled_entry = 1
	gle.update(args)
	if args.is_cancelled == 1  and args.custom_reconciled_entry == 1:
		gle.posting_date = frappe.utils.today()
	# frappe.throw(f"HI{gle.posting_date}")
	# frappe.throw(f"{args, adv_adj, update_outstanding,gle.posting_date}")
	gle.flags.ignore_permissions = 1
	gle.flags.from_repost = from_repost
	gle.flags.adv_adj = adv_adj
	gle.flags.update_outstanding = update_outstanding or "Yes"
	gle.flags.notify_update = False
	gle.submit()

	if not from_repost and gle.voucher_type != "Period Closing Voucher":
		validate_expense_against_budget(args)
