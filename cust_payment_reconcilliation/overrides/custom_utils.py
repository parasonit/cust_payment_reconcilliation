import frappe
import erpnext
from erpnext.accounts.utils import (
	_delete_pl_entries,
	check_if_advance_entry_modified,
	validate_allocated_amount,
	_build_dimensions_dict_for_exc_gain_loss,
	update_reference_in_journal_entry,
	update_reference_in_payment_entry,
	create_payment_ledger_entry,
	update_voucher_outstanding
	)
from erpnext.controllers.accounts_controller import AccountsController
from cust_payment_reconcilliation.overrides.custom_payment_entry import (custom_make_gl_entries,custom_make_advance_gl_entries)
def custom_reconcile_against_document(
	args, skip_ref_details_update_for_pe=False, active_dimensions=None,clearing_date=None
):  # nosemgrep
	"""
	Cancel PE or JV, Update against document, split if required and resubmit
	"""
	# To optimize making GL Entry for PE or JV with multiple references
	reconciled_entries = {}
	for row in args:
		if not reconciled_entries.get((row.voucher_type, row.voucher_no)):
			reconciled_entries[(row.voucher_type, row.voucher_no)] = []

		reconciled_entries[(row.voucher_type, row.voucher_no)].append(row)

	for key, entries in reconciled_entries.items():
		voucher_type = key[0]
		voucher_no = key[1]

		# cancel advance entry
		doc = frappe.get_doc(voucher_type, voucher_no)
		frappe.flags.ignore_party_validation = True

		# When Advance is allocated from an Order to an Invoice
		# whole ledger must be reposted
		repost_whole_ledger = any([x.voucher_detail_no for x in entries])
		if voucher_type == "Payment Entry" and doc.book_advance_payments_in_separate_party_account:
			if repost_whole_ledger:
				custom_make_gl_entries(doc,cancel=1,clearing_date=clearing_date)
			else:
				custom_make_advance_gl_entries(doc,cancel=1,clearing_date=clearing_date)
		else:
			_delete_pl_entries(voucher_type, voucher_no)

		for entry in entries:
			check_if_advance_entry_modified(entry)
			validate_allocated_amount(entry)
			# if entry.against_voucher_type == "Sales Invoice":
			# 	against_voucher_account = frappe.db.get_value(entry.against_voucher_type, entry.against_voucher, "debit_to")
			# elif entry.against_voucher_type == "Purchase Invoice":
			# 	against_voucher_account = frappe.db.get_value(entry.against_voucher_type, entry.against_voucher, "credit_to")
			# else:
			# 	against_voucher_account = None
			dimensions_dict = _build_dimensions_dict_for_exc_gain_loss(entry, active_dimensions)

			# update ref in advance entry
			if voucher_type == "Journal Entry":
				referenced_row, update_advance_paid = update_reference_in_journal_entry(
					entry, doc, do_not_save=False
				)
				# advance section in sales/purchase invoice and reconciliation tool,both pass on exchange gain/loss
				# amount and account in args
				# referenced_row is used to deduplicate gain/loss journal
				
                
                # voucher_data = frappe.db.get_value("Journal Entry Account", entry.voucher_detail_no, ["account", "debit", "exchange_rate", "cost_center"])
				# if voucher_data:
				# 	voucher_account, debit, exchange_rate, cost_center = voucher_data
				# else:
				# 	# Handle the case where no matching record is found
				# 	voucher_account = debit = exchange_rate = cost_center = None
				# if debit:
				# 	voucher_account_amt_field = "credit_in_account_currency"
				# 	against_voucher_account_amt_field = "debit_in_account_currency"
				# else:
				# 	voucher_account_amt_field = "debit_in_account_currency"
				# 	against_voucher_account_amt_field = "credit_in_account_currency"
				entry.update({"referenced_row": referenced_row})
				AccountsController.make_exchange_gain_loss_journal(doc,[entry], dimensions_dict)
				# db14_check = frappe.db.get_value("Journal Entry Account",{"parent":entry.voucher_no,"credit_in_account_currency":entry.allocated_amount},"custom_db14")
				# cus_exchange_rate = frappe.db.get_value("Journal Entry Account",{"parent":entry.voucher_no,"credit_in_account_currency":entry.allocated_amount},"exchange_rate")
				# if db14_check == 1:
				# 	make_revarse_journal_entry(entry, doc,against_voucher_account,voucher_account,voucher_account_amt_field,against_voucher_account_amt_field,cost_center,cus_exchange_rate, do_not_save=False)
			else:
				referenced_row, update_advance_paid = update_reference_in_payment_entry(
					entry,
					doc,
					do_not_save=True,
					skip_ref_details_update_for_pe=skip_ref_details_update_for_pe,
					dimensions_dict=dimensions_dict,
				)
		doc.save(ignore_permissions=True)
		# re-submit advance entry
		doc = frappe.get_doc(entry.voucher_type, entry.voucher_no)

		if voucher_type == "Payment Entry" and doc.book_advance_payments_in_separate_party_account:
			# When Advance is allocated from an Order to an Invoice
			# whole ledger must be reposted
			if repost_whole_ledger:
				custom_make_gl_entries(doc,clearing_date=clearing_date)
			else:
				# both ledgers must be posted to for `Advance` in separate account feature
				# TODO: find a more efficient way post only for the new linked vouchers
				custom_make_advance_gl_entries(doc,clearing_date=clearing_date)
		else:
			gl_map = doc.build_gl_map()
			# Make sure there is no overallocation
			from erpnext.accounts.general_ledger import process_debit_credit_difference

			process_debit_credit_difference(gl_map)
			create_payment_ledger_entry(gl_map, update_outstanding="No", cancel=0, adv_adj=1)

		# Only update outstanding for newly linked vouchers
		for entry in entries:
			update_voucher_outstanding(
				entry.against_voucher_type,
				entry.against_voucher,
				entry.account,
				entry.party_type,
				entry.party,
			)
		# update advance paid in Advance Receivable/Payable doctypes
		if update_advance_paid:
			for t, n in update_advance_paid:
				frappe.get_doc(t, n).set_total_advance_paid()

		frappe.flags.ignore_party_validation = False