import frappe
from frappe.utils import getdate

from erpnext.accounts.general_ledger import (
	# make_gl_entries,
	make_reverse_gl_entries,
	process_gl_map,
)
from erpnext.controllers.accounts_controller import AccountsController
from cust_payment_reconcilliation.overrides.custom_general_ledger import custom_gl_make_gl_entries
from erpnext.accounts.utils import (
	cancel_exchange_gain_loss_journal)

def custom_make_gl_entries(self, cancel=0, adv_adj=0,clearing_date=None):
		frappe.throw(f"{self,clearing_date}from cust utils custom_make_gl_entries")
		gl_entries = self.build_gl_map()
		gl_entries = process_gl_map(gl_entries)
		custom_gl_make_gl_entries(gl_entries, cancel=cancel, adv_adj=adv_adj,clearing_date=clearing_date)
		if cancel:
			cancel_exchange_gain_loss_journal(frappe._dict(doctype=self.doctype, name=self.name))
		else:
			AccountsController.make_exchange_gain_loss_journal(self)

		custom_make_advance_gl_entries(self,cancel=cancel,clearing_date=clearing_date)
		
def custom_make_advance_gl_entries(
		
		self, entry: object | dict = None, cancel: bool = 0, update_outstanding: str = "Yes",clearing_date=None
	):
		# frappe.throw(f"{self,clearing_date}from cust utils custom_make_advance_gl_entries")
		gl_entries = []
		custom_add_advance_gl_entries(self,gl_entries, entry,clearing_date=clearing_date)

		if cancel:
			make_reverse_gl_entries(gl_entries, partial_cancel=True)
		else:
			custom_gl_make_gl_entries(gl_entries, update_outstanding=update_outstanding,clearing_date=clearing_date)

def custom_add_advance_gl_entries(self, gl_entries: list, entry: object | dict | None,clearing_date=None):
    """
    If 'entry' is passed, GL entries only for that reference is added.
    """
    if self.book_advance_payments_in_separate_party_account:
        references = [x for x in self.get("references")]
        if entry:
            references = [x for x in self.get("references") if x.name == entry.name]

        for ref in references:
            if ref.reference_doctype in (
                "Sales Invoice",
                "Purchase Invoice",
                "Journal Entry",
                "Payment Entry",
            ):
                add_advance_gl_for_reference(self,gl_entries, ref,clearing_date)

def add_advance_gl_for_reference(self, gl_entries, invoice,clearing_date=None):
		args_dict = {
			"party_type": self.party_type,
			"party": self.party,
			"account_currency": self.party_account_currency,
			"cost_center": self.cost_center,
			"voucher_type": "Payment Entry",
			"voucher_no": self.name,
			"voucher_detail_no": invoice.name,
		}

		if self.reconcile_on_advance_payment_date:
			posting_date = self.posting_date
		else:
			date_field = "posting_date"
			if invoice.reference_doctype in ["Sales Order", "Purchase Order"]:
				date_field = "transaction_date"
			posting_date = frappe.db.get_value(invoice.reference_doctype, invoice.reference_name, date_field)

			if getdate(posting_date) < getdate(self.posting_date):
				posting_date = self.posting_date
		if clearing_date:
			posting_date =clearing_date
		dr_or_cr, account = self.get_dr_and_account_for_advances(invoice)
		args_dict["account"] = account
		args_dict[dr_or_cr] = self.calculate_base_allocated_amount_for_reference(invoice)
		args_dict[dr_or_cr + "_in_account_currency"] = invoice.allocated_amount
		args_dict.update(
			{
				"against_voucher_type": invoice.reference_doctype,
				"against_voucher": invoice.reference_name,
				"posting_date": posting_date,
			}
		)
		gle = self.get_gl_dict(
			args_dict,
			item=self,
		)
		gl_entries.append(gle)

		args_dict[dr_or_cr] = 0
		args_dict[dr_or_cr + "_in_account_currency"] = 0
		dr_or_cr = "debit" if dr_or_cr == "credit" else "credit"
		args_dict["account"] = self.party_account
		args_dict[dr_or_cr] = self.calculate_base_allocated_amount_for_reference(invoice)
		args_dict[dr_or_cr + "_in_account_currency"] = invoice.allocated_amount
		args_dict.update(
			{
				"against_voucher_type": "Payment Entry",
				"against_voucher": self.name,
			}
		)
		gle = self.get_gl_dict(
			args_dict,
			item=self,
		)
		gl_entries.append(gle)
