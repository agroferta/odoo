# Copyright 2018 Vauxoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from odoo import models, fields, api, _
from odoo.tools import float_is_zero
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.depends('l10n_mx_edi_origin', 'amount_total')
    def _compute_amount_advances(self):
        w_advance = self.filtered(
            lambda i: i.company_id.l10n_mx_edi_advance == 'A' and i.move_type == 'out_invoice' and
            i.l10n_mx_edi_origin and i.l10n_mx_edi_origin.startswith('07'))
        for record in self - w_advance:
            record.l10n_mx_edi_amount_advances = 0.0
            record.l10n_mx_edi_amount_residual_advances = record.amount_total

        for record in w_advance:
            if record.state == 'draft':
                adv_amount, _partial_amount, _lines, _reverse_lines, _partial_line = record._l10_mx_edi_prepare_advance_refund_fields()  # noqa
            else:
                reverse_entries = self.search(
                    [('reversed_entry_id', '=', self.id)])
                credit_note = reverse_entries.filtered(
                    lambda i: i._l10n_mx_edi_get_advance_uuid_related() and
                    i.state not in ('draft', 'cancel'))
                adv_amount = sum(credit_note.mapped('amount_total'))
            record.l10n_mx_edi_amount_advances = adv_amount
            record.l10n_mx_edi_amount_residual_advances = record.amount_total - adv_amount  # noqa

    l10n_mx_edi_amount_residual_advances = fields.Monetary(
        'Amount residual with advances', compute='_compute_amount_advances',
        help='Save the amount that will be applied as advance when validate '
        'the invoice')
    l10n_mx_edi_amount_advances = fields.Monetary(
        'Amount in advances', compute='_compute_amount_advances',
        help='Save the amount that will be applied as advance when validate '
        'the invoice')

    def _compute_payments_widget_to_reconcile_info(self):
        res = super(
            AccountMove, self)._compute_payments_widget_to_reconcile_info()
        for move in self.filtered(lambda inv: inv.state == 'draft' and
                                  inv.move_type == 'out_invoice'):
            domain = move._l10n_mx_edi_get_advance_aml_domain()
            domain.extend([('move_id.payment_state', 'in', ['paid', 'in_payment', 'partial'])])
            related_advs = move._l10n_mx_edi_get_advance_uuid_related()
            for uuid in related_advs:
                domain.extend([('move_id.l10n_mx_edi_cfdi_uuid', 'not like', uuid)])
                domain.extend([('move_id.narration', 'not like', uuid)])
            lines = move.env['account.move.line'].search(domain)
            if not lines:
                return res
            info = {'title': _('Outstanding credits as Advance'),
                    'outstanding': True,
                    'content': [],
                    'move_id': move.id}
            currency_id = move.currency_id
            for line in lines:
                # get the outstanding residual value in invoice currency
                if line.currency_id and line.currency_id == currency_id:
                    amount_to_show = abs(line.amount_residual_currency)
                else:
                    currency = line.company_id.currency_id
                    amount_to_show = currency._convert(
                        abs(line.amount_residual), currency_id,
                        move.company_id, line.date or fields.Date.today())
                taxes = line.tax_ids.compute_all(
                    amount_to_show, line.currency_id or line.company_id.currency_id, 1)['taxes']
                amount_to_show += sum([tax.get('amount') for tax in taxes])
                if float_is_zero(
                        amount_to_show,
                        precision_rounding=currency_id.rounding):
                    continue
                info['content'].append({
                    'journal_name': line.ref or line.move_id.name,
                    'amount': amount_to_show,
                    'currency': currency_id.symbol,
                    'id': line.id,
                    'position': currency_id.position,
                    'digits': [69, currency_id.decimal_places], })
            if not info['content']:
                return res
            self.invoice_outstanding_credits_debits_widget = json.dumps(info)
            self.invoice_has_outstanding = True
        return res

    def js_assign_outstanding_line(self, line_id):
        """Related an advance to the invoice."""
        res = super(AccountMove, self).js_assign_outstanding_line(line_id)
        credit_aml = self.env['account.move.line'].browse(line_id)
        advance = credit_aml.move_id
        for invoice in self.filtered(lambda r: r.state == 'draft'):
            invoice.l10n_mx_edi_origin = invoice._l10n_mx_edi_write_cfdi_origin(
                '07', [advance.l10n_mx_edi_cfdi_uuid])
            if invoice.company_id.l10n_mx_edi_advance != 'B':
                continue
            if credit_aml.currency_id and credit_aml.currency_id == invoice.currency_id:  # noqa
                amount = abs(credit_aml.amount_residual_currency)
            else:
                currency = credit_aml.company_id.currency_id
                amount = currency._convert(
                    abs(credit_aml.amount_residual), invoice.currency_id,
                    invoice.company_id, credit_aml.date or fields.Date.today())
            if amount > invoice.amount_untaxed:
                amount = invoice.amount_untaxed
            adv_text = ' - CFDI por remanente de un anticipo'
            invoice_total = invoice.amount_untaxed
            for line in invoice.invoice_line_ids:
                total_discount = amount / invoice_total * line.price_subtotal
                line.write({
                    'name': '%s%s' % (
                        line.name.replace(adv_text, ''), adv_text),
                    'l10n_mx_edi_total_discount': total_discount + line.l10n_mx_edi_total_discount,
                })
        return res

    def _l10n_mx_edi_is_advance(self):
        """Check if an invoice is an advance"""
        self.ensure_one()
        if self.move_type != 'out_invoice' or len(self.invoice_line_ids) != 1:
            return False
        advance_product = self.company_id.l10n_mx_edi_product_advance_id
        if self.invoice_line_ids.product_id.id != advance_product.id:
            return False
        return True

    def _l10n_mx_edi_get_advance_uuid_related(self):
        """return the advance's uuid applied"""
        self.ensure_one()
        if not self.l10n_mx_edi_origin:
            return []
        related_docs = self._l10n_mx_edi_read_cfdi_origin(self.l10n_mx_edi_origin)
        if related_docs[0] == '07':
            return related_docs[1]
        return []

    def _l10n_mx_edi_get_advance_aml_domain(self):
        """Get domain for available advances"""
        self.ensure_one()
        adv_prod = self.company_id.l10n_mx_edi_product_advance_id
        financial_partner = self.partner_id._find_accounting_partner(
            self.partner_id)
        domain = [('account_id', '=', adv_prod.property_account_income_id.id),
                  ('partner_id', '=', financial_partner.id),
                  ('reconciled', '=', False),
                  '|', ('amount_residual', '!=', 0.0),
                  ('amount_residual_currency', '!=', 0.0),
                  ('credit', '>', 0), ('debit', '=', 0),
                  ('move_id.state', '=', 'posted')]
        return domain

    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line_ids(self):
        """Set values when the invoice is an advance"""
        res = super(AccountMove, self)._onchange_invoice_line_ids()
        if not self._l10n_mx_edi_is_advance():
            return res
        self.update({
            'invoice_payment_term_id': self.env.ref(
                'account.account_payment_term_immediate'),
            'l10n_mx_edi_origin': False,
        })
        self.invoice_line_ids.name = 'Anticipo del bien o servicio'
        return res

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        res = super(AccountMove, self)._onchange_partner_id()
        if self._l10n_mx_edi_is_advance:
            self._onchange_invoice_line_ids()
        return res

    def action_post(self):
        """Create the credit note for advances and reconcile it with
        the invoice (only when this one has advances and it's signed).
        """
        res = super().action_post()
        with_advance = self.filtered(lambda r: r.move_type == 'out_invoice' and r.company_id.l10n_mx_edi_advance == 'A'
                                     and r._l10n_mx_edi_get_advance_uuid_related())
        advance_b = self.filtered(lambda r: r.move_type == 'out_invoice' and r.company_id.l10n_mx_edi_advance == 'B'
                                  and r._l10n_mx_edi_get_advance_uuid_related())

        if not with_advance:
            return res

        for inv in with_advance:
            adv_amount, _partial_amount, lines, _reverse_lines, _partial_line = inv._l10_mx_edi_prepare_advance_refund_fields()  # noqa
            if not adv_amount:
                inv.message_post(body=_(
                    '<p>The credit note was not created because the advance '
                    'was used in another invoice or it is not in this '
                    'system.</p>'
                    '<p>So please, follow one of these actions:</p>'
                    '<li>Cancel this invoice and remove the related advance.'
                    '</li><li>Create the credit note manually.</li>'))
                continue
            inv.with_context(edi_test_mode=False).edi_document_ids._process_documents_web_services()
            refund = self.env['account.move.reversal'].with_context(
                active_ids=inv.ids, active_model='account.move', edi_test_mode=False).create({
                    'refund_method': 'cancel',
                    'reason': 'Aplicación de anticipos',
                    'date': inv.invoice_date, })
            refund = refund.reverse_moves()
            inv.reversal_move_id.write({'l10n_mx_edi_origin': '07|%s' % inv.l10n_mx_edi_cfdi_uuid})
            account = inv.company_id.l10n_mx_edi_product_advance_id.property_account_income_id
            moves = inv.reversal_move_id.line_ids.filtered(lambda line: line.account_id == account)
            moves |= lines.filtered(lambda line: line.account_id == account)
            moves.reconcile()
            reverse_entries = self.search(
                [('reversed_entry_id', '=', self.id)])
            inv.message_post_with_view(
                'l10n_mx_edi_advance.l10n_mx_edi_message_advance_refund',
                values={'self': inv, 'origin': reverse_entries},
                subtype_id=self.env.ref('mail.mt_note').id)
        for inv in advance_b:
            adv_amount, _partial_amount, lines, reverse_lines, _partial_line = inv._l10_mx_edi_prepare_advance_refund_fields()  # noqa
            aml_obj = inv.move_id.line_ids.with_context(check_move_validity=False, recompute=False)
            account = inv.company_id.l10n_mx_edi_product_advance_id.categ_id.property_account_income_categ_id or inv.company_id.l10n_mx_edi_product_advance_id.property_account_income_id  # noqa
            move_line_dict = {
                'name': _('Advance'),
                'move_id': inv.move_id,
                'company_id': inv.company_id,
                'quantity': 1,
                'debit': 0,
                'credit': inv.currency_id._convert(
                    adv_amount, inv.company_id.currency_id, inv.company_id, inv.invoice_date),
                'account_id': account.id,
                'invoice_id': inv,
                'partner_id': inv.partner_id,
                'currency_id': inv.currency_id if inv.currency_id != inv.company_id.currency_id else False,
                'amount_currency': -adv_amount if inv.currency_id != inv.company_id.currency_id else 0,
            }
            first_line = aml_obj.new(move_line_dict)
            first_line = aml_obj._convert_to_write(first_line._cache)
            aml_obj.create(first_line)
            move_line_dict.update({
                'debit': inv.currency_id._convert(
                    adv_amount, inv.company_id.currency_id, inv.company_id, inv.invoice_date),
                'credit': 0,
                'account_id': inv.company_id.l10n_mx_edi_product_advance_id.property_account_income_id,
                'amount_currency': adv_amount if inv.currency_id != inv.company_id.currency_id else 0,
            })
            second_line = aml_obj.new(move_line_dict)
            second_line = aml_obj._convert_to_write(second_line._cache)
            second_line = aml_obj.create(second_line)
            inv.finalize_invoice_move_lines(second_line | reverse_lines)
            (second_line | reverse_lines).reconcile()
        return res

    @api.model
    def _reverse_move_vals(self, default_values, cancel=True):
        """Assign values for a CFDI credit note and advance
            - CFDI origin.
            - Payment method
            - Usage: 'G02' - returns, discounts or bonuses.
        """
        if self.l10n_mx_edi_cfdi_request in ('on_invoice', 'on_refund'):
            default_values.update({
                'l10n_mx_edi_payment_method_id':
                self.l10n_mx_edi_payment_method_id.id,
                'l10n_mx_edi_usage': 'G02',
            })
        values = super(AccountMove, self)._reverse_move_vals(
            default_values, cancel)
        adv_amount, _partial_amount, lines, _reverse_lines, _partial_line = self._l10_mx_edi_prepare_advance_refund_fields()  # noqa
        reverse_entries = self.search([('reversed_entry_id', '=', self.id)])
        if (reverse_entries or not adv_amount or
                not self._l10n_mx_edi_get_advance_uuid_related()):
            return values
        self.refresh()
        if not self.l10n_mx_edi_cfdi_uuid:
            raise UserError(_('The invoice is not signed, and the UUID is '
                              'required to relate the documents.'))
        values['l10n_mx_edi_payment_method_id'] = self.env.ref(
            'l10n_mx_edi.payment_method_anticipos').id
        advances = lines.mapped('move_id')
        if not advances:
            return values
        adv_prod = self.company_id.l10n_mx_edi_product_advance_id
        taxes = adv_prod.taxes_id
        percentage = sum(tax.amount for tax in taxes if not tax.price_include)
        price_unit = adv_amount * 100 / (100 + percentage)
        invoice_line_ids = [(0, 0, {
            'name': 'Aplicación de anticipo',
            'price_unit': price_unit,
            'account_id': adv_prod.property_account_income_id.id,
            'product_id': adv_prod.id,
            'product_uom_id': adv_prod.uom_id.id,
            'tax_ids': [(6, 0, taxes.ids)],
        })]
        values.pop('line_ids')
        values['invoice_line_ids'] = invoice_line_ids
        return values

    @api.returns('self')
    def advance(self, partner, amount, currency):
        """Create an advance"""
        company = self.env.context.get('company_id') or self.env.company.id
        company = self.env['res.company'].browse(company)
        product = company.l10n_mx_edi_product_advance_id
        journal = self._search_default_journal(['sale'])
        prod_accounts = product.product_tmpl_id.get_product_accounts()
        advance = self.new({
            'partner_id': partner.id,
            'currency_id': currency.id,
            'move_type': 'out_invoice',
            'invoice_payment_term_id': self.env.ref(
                'account.account_payment_term_immediate').id,
            'l10n_mx_edi_origin': False,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': 'Anticipo del bien o servicio',
                'account_id': prod_accounts['income'].id,
                'product_uom_id': product.uom_id.id,
                'quantity': 1,
                'price_unit': 0.0,
            })],
        })
        advance.invoice_line_ids._onchange_account_id()
        # get amount for price unit if there is a tax
        taxes = advance.invoice_line_ids.tax_ids
        percentage = sum(tax.amount for tax in taxes if not tax.price_include)
        price_unit = amount * 100 / (100 + percentage)
        advance.invoice_line_ids.price_unit = price_unit
        advance = self._convert_to_write(advance._cache)
        advance = self.create(advance)
        return advance

    def _l10_mx_edi_prepare_advance_refund_fields(self):
        """ Helper function to get the amounts and amls to apply in the
        credit note for the advances
        """
        self.ensure_one()
        adv_amount = partial_amount = 0.0
        reverse_lines = self.env['account.move.line']
        partial_line = reverse_lines
        domain = self._l10n_mx_edi_get_advance_aml_domain()
        related_advs = self._l10n_mx_edi_get_advance_uuid_related()
        for uuid in related_advs:
            if uuid != related_advs[-1]:
                domain.extend('|')
            domain.extend([('move_id.l10n_mx_edi_cfdi_uuid', 'like', uuid)])
        lines = self.env['account.move.line'].search(domain)
        if not lines:
            return adv_amount, partial_amount, lines, reverse_lines, partial_line  # noqa
        for line in lines:
            if adv_amount >= self.amount_total:
                break
            # get the outstanding residual value in invoice currency
            if line.currency_id and line.currency_id == self.currency_id:
                amount = abs(line.amount_residual_currency)
            else:
                currency = line.company_id.currency_id
                amount = currency._convert(
                    abs(line.amount_residual), self.currency_id,
                    self.company_id, line.date or fields.Date.today())
                if float_is_zero(
                        amount, precision_rounding=self.currency_id.rounding):
                    continue
            adv_amount += amount
            if self.company_id.l10n_mx_edi_advance != 'B':
                taxes = line.tax_ids.compute_all(
                    amount, line.currency_id or line.company_id.currency_id, 1)['taxes']
                adv_amount += sum([tax.get('amount') for tax in taxes])
            adv_discount = 0
            if self.company_id.l10n_mx_edi_advance == 'B':
                adv_discount = self.l10n_mx_edi_total_discount
            reverse_lines |= line
            if adv_amount > self.amount_total + adv_discount:
                partial_amount = adv_amount - self.amount_total + adv_discount
                adv_amount = self.amount_total + adv_discount
                partial_line = line
        return adv_amount, partial_amount, lines, reverse_lines, partial_line


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def _compute_amount_fields(self, amount, src_currency, company_currency):
        """ Helper function to compute value for fields
        debit/credit/amount_currency based on an amount and the currencies
        given in parameter"""
        # TODO - Remove method
        amount_currency = False
        currency_id = False
        date = self.env.context.get('date') or fields.Date.today()
        company = self.env.context.get('company_id')
        company = self.env['res.company'].browse(
            company) if company else self.env.user.company_id
        if src_currency and src_currency != company_currency:
            amount_currency = amount
            amount = src_currency._convert(
                amount, company_currency, company, date)
            currency_id = src_currency.id
        debit = amount if amount > 0 else 0.0
        credit = -amount if amount < 0 else 0.0
        return debit, credit, amount_currency, currency_id
