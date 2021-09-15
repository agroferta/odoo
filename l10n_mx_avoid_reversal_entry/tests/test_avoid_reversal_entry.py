# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo.addons.l10n_mx_edi.tests.common import TestMxEdiCommon


class TestL10nMxTaxCashBasis(TestMxEdiCommon):

    def setUp(self):
        super(TestL10nMxTaxCashBasis, self).setUp()
        self.account_move_model = self.env['account.move']
        self.account_model = self.env['account.account']
        self.register_payments_model = self.env['account.payment.register']
        self.today = (self.env['l10n_mx_edi.certificate'].sudo().
                      get_mx_current_datetime())
        self.mxn = self.env.ref('base.MXN')
        self.usd = self.env.ref('base.USD')
        company = self.invoice.company_id
        company.write({'currency_id': self.mxn.id})
        self.tax_cash_basis_journal_id = company.tax_cash_basis_journal_id
        self.curr_ex_journal_id = company.currency_exchange_journal_id
        self.user_type_id = self.env.ref(
            'account.data_account_type_current_liabilities')
        self.payment_method_manual_out = self.env.ref(
            'account.account_payment_method_manual_out')
        self.payment_method_manual_in = self.env.ref(
            'account.account_payment_method_manual_in')
        self.bank_journal_mxn = self.env['account.journal'].create(
            {'name': 'Bank MXN',
             'type': 'bank',
             'code': 'BNK37',
             })
        self.journal = self.env['account.journal'].search(
            [('type', '=', 'purchase'),
             ('company_id', '=', self.invoice.company_id.id)], limit=1)
        self.iva_tag = self.env['account.account.tag'].search([('name', '=', 'IVA')])
        self.tax_account = self.create_account(
            '11111101', 'Tax Account')
        cash_tax_account = self.create_account(
            '77777777', 'Cash Tax Account')
        account_tax_cash_basis = self.create_account(
            '99999999', 'Tax Base Account')
        self.tax_16.write({
            'tax_exigibility': 'on_payment',
            'type_tax_use': 'purchase',
            'cash_basis_transition_account_id': cash_tax_account.id,
        })
        self.tax_16.company_id.write({
            'account_cash_basis_base_account_id': account_tax_cash_basis.id,
        })
        self.tax_16.invoice_repartition_line_ids.write({'account_id': self.tax_account.id})
        self.tax_16.refund_repartition_line_ids.write({'account_id': self.tax_account.id})
        self.product.supplier_taxes_id = [self.tax_16.id]

        self.set_currency_rates(mxn_rate=21, usd_rate=1)

    def create_payment(self, invoice, date, journal, currency):
        statement = self.env['account.bank.statement'].with_context(edi_test_mode=True).create({
            'name': 'test_statement',
            'date': date,
            'journal_id': journal.id,
            'currency_id': currency.id,
            'line_ids': [
                (0, 0, {
                    'payment_ref': 'mx_st_line',
                    'partner_id': invoice.partner_id.id,
                    'amount': -invoice.amount_total,
                }),
            ],
        })
        statement.button_post()
        receivable_line = invoice.line_ids.filtered(lambda line: line.account_internal_type == 'payable')
        statement.line_ids.reconcile([{'id': receivable_line.id}])
        return statement.line_ids.move_id

    def delete_journal_data(self):
        """Delete journal data
        delete all journal-related data, so a new currency can be set.
        """

        # 1. Reset to draft moves (invoices), so some records may be deleted
        company = self.invoice.company_id
        moves = self.env['account.move'].search(
            [('company_id', '=', company.id)])
        moves.button_draft()
        # 2. Delete related records
        models_to_clear = [
            'account.move.line', 'account.payment',
            'account.bank.statement']
        for model in models_to_clear:
            records = self.env[model].search([('company_id', '=', company.id)])
            records.unlink()

    def create_account(self, code, name, user_type_id=False):
        """This account is created to use like cash basis account and only
        it will be filled when there is payment
        """
        return self.account_model.create({
            'name': name,
            'code': code,
            'user_type_id': user_type_id or self.user_type_id.id,
        })

    def test_instead_of_reverting_entry_delete_it(self):
        """What I expect from here:
            - On Payment unreconciliation cash flow journal entry is deleted
        """
        self.delete_journal_data()
        self.tax_account.write({'reconcile': True})
        self.env['res.config.settings'].write({'group_multi_currency': True})
        cash_am_ids = self.env['account.move'].search([('journal_id', 'in', self.tax_cash_basis_journal_id.ids)])
        self.assertFalse(cash_am_ids, 'There should be no journal entry')

        invoice_date = self.today - timedelta(days=1)
        invoice_id = self.invoice.copy({
            'move_type': 'in_invoice',
            'currency_id': self.usd.id,
            'date': invoice_date.date(),
            'invoice_date': invoice_date.date(),
            'journal_id': self.journal.id,
        })

        invoice_id.line_ids.unlink()
        invoice_id.invoice_line_ids = [(0, 0, {
            'account_id': self.product.product_tmpl_id.get_product_accounts()['income'].id,
            'product_id': self.product.id,
            'quantity': 1,
            'price_unit': 450,
            'product_uom_id': self.product.uom_id.id,
            'name': self.product.name,
            'tax_ids': [(6, 0, self.tax_16.ids)],
        })]
        invoice_id.action_post()
        self.create_payment(invoice_id, self.today, self.bank_journal_mxn, self.usd)
        cash_am_ids = self.env['account.move'].search([('journal_id', 'in', self.tax_cash_basis_journal_id.ids)])
        self.assertEqual(len(cash_am_ids), 1, 'There should be one journal entry')
        invoice_id.line_ids.sudo().remove_move_reconcile()

        cash_am_ids = self.env['account.move'].search([('journal_id', 'in', self.tax_cash_basis_journal_id.ids)])
        self.assertFalse(cash_am_ids, 'There should be no journal entry')

    def test_reverting_exchange_difference_from_non_mxn(self):
        self.delete_journal_data()
        self.invoice.company_id.write({
            'currency_id': self.usd.id,
            'country_id': self.env.ref('base.us').id,
        })

        cash_am_ids = self.env['account.move'].search([('journal_id', 'in', self.curr_ex_journal_id.ids)])
        self.assertFalse(cash_am_ids, 'There should be no journal entry')

        invoice_date = self.today - timedelta(days=1)
        invoice_id = self.invoice.copy({
            'move_type': 'in_invoice',
            'currency_id': self.env.ref('base.MXN').id,
            'date': invoice_date.date(),
            'invoice_date': invoice_date.date(),
            'journal_id': self.journal.id,
        })

        invoice_id.line_ids.unlink()
        invoice_id.invoice_line_ids = [(0, 0, {
            'account_id': self.product.product_tmpl_id.get_product_accounts()['income'].id,
            'product_id': self.product.id,
            'quantity': 1,
            'price_unit': 450,
            'product_uom_id': self.product.uom_id.id,
            'name': self.product.name,
            'tax_ids': [(6, 0, self.tax_16.ids)],
        })]
        invoice_id.action_post()

        self.create_payment(invoice_id, self.today, self.bank_journal_mxn, self.mxn)
        cash_am_ids = self.env['account.move'].search([('journal_id', 'in', self.curr_ex_journal_id.ids)])
        self.assertEqual(len(cash_am_ids), 1, 'There should be One journal entry')

        invoice_id.line_ids.sudo().remove_move_reconcile()
        cash_am_ids = self.env['account.move'].search([('journal_id', 'in', self.curr_ex_journal_id.ids)])
        self.assertEqual(len(cash_am_ids), 2, 'There should be two journal entry')

    def set_currency_rates(self, mxn_rate, usd_rate):
        date = (self.env['l10n_mx_edi.certificate'].sudo().get_mx_current_datetime().date())
        self.mxn.rate_ids.filtered(lambda r: r.name == date).unlink()
        self.mxn.rate_ids = self.env['res.currency.rate'].create({
            'rate': mxn_rate, 'name': date, 'currency_id': self.mxn.id})
        self.usd.rate_ids.filtered(lambda r: r.name == date).unlink()
        self.usd.rate_ids = self.env['res.currency.rate'].create({
            'rate': usd_rate, 'name': date, 'currency_id': self.usd.id})
