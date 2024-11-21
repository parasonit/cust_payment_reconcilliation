import frappe
import erpnext
from frappe.model.document import Document
from erpnext.accounts.doctype.payment_reconciliation.payment_reconciliation import (
    PaymentReconciliation,
    adjust_allocations_for_taxes,
    reconcile_dr_cr_note,
)

from cust_payment_reconcilliation.overrides.custom_utils import custom_reconcile_against_document

# class CustomPaymentReconciliation(Document):
def reconcile_allocations(self, skip_ref_details_update_for_pe=False):
    # frappe.throw(f"{self.clearing_date}from custom")
    adjust_allocations_for_taxes(self)
    dr_or_cr = (
        "credit_in_account_currency"
        if erpnext.get_party_account_type(self.party_type) == "Receivable"
        else "debit_in_account_currency"
    )

    entry_list = []
    dr_or_cr_notes = []
    for row in self.get("allocation"):
        reconciled_entry = []
        if row.invoice_number and row.allocated_amount:
            if row.reference_type in ["Sales Invoice", "Purchase Invoice"]:
                reconciled_entry = dr_or_cr_notes
            else:
                reconciled_entry = entry_list

            payment_details = self.get_payment_details(row, dr_or_cr)
            payment_details["default_advance_account"] = self.default_advance_account
            reconciled_entry.append(payment_details)

    if entry_list:
        custom_reconcile_against_document(entry_list, skip_ref_details_update_for_pe, self.dimensions,self.clearing_date)

    if dr_or_cr_notes:
        reconcile_dr_cr_note(dr_or_cr_notes, self.company, self.dimensions)