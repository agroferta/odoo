from odoo import api, fields, models
from odoo.tools import float_round


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    l10n_mx_edi_amount_discount = fields.Monetary(
        "Unit Discount",
        compute='_compute_l10n_mx_edi_amount_discount',
        inverse='_inverse_discount',
        store=True,
        help="Discount to be applied for each product in the invoice lines ",
    )
    l10n_mx_edi_total_discount = fields.Monetary(
        "Total Discount",
        compute='_compute_l10n_mx_edi_total_discount',
        inverse='_inverse_total_discount',
        store=True,
        help="Total discount per invoice line. The formula is discount * "
             "quantity of products on the invoice.",
    )

    @api.depends('discount', 'price_unit', 'quantity')
    def _compute_l10n_mx_edi_amount_discount(self):
        deci_pre = self.env['decimal.precision']
        discount_digits = deci_pre.precision_get('Discount')
        sale_price_digits = deci_pre.precision_get('Product Price')
        for line in self:
            discount = float_round(
                float_round(line.price_unit,
                            precision_digits=sale_price_digits) *
                float_round(line.discount,
                            precision_digits=discount_digits) /
                100.0,
                precision_digits=discount_digits
            )
            line.l10n_mx_edi_amount_discount = discount

    @api.onchange('l10n_mx_edi_amount_discount')
    def onchange_l10n_mx_edi_amount_discount(self):
        deci_pre = self.env['decimal.precision']
        discount_digits = deci_pre.precision_get('Discount')
        for line in self:
            if not line.price_unit or not line.quantity:
                continue
            total_discount = (line.l10n_mx_edi_amount_discount *
                              float_round(
                                  line.quantity,
                                  precision_digits=discount_digits))
            discount = float_round(
                float_round(line.l10n_mx_edi_total_discount,
                            precision_digits=discount_digits) /
                float_round(line.quantity,
                            precision_digits=discount_digits),
                precision_digits=discount_digits
            )
            line.l10n_mx_edi_total_discount = total_discount
            line.discount = float_round(
                discount / line.price_unit * 100,
                precision_digits=discount_digits)

    @api.depends('l10n_mx_edi_amount_discount')
    def _compute_l10n_mx_edi_total_discount(self):
        deci_pre = self.env['decimal.precision']
        discount_digits = deci_pre.precision_get('Discount')
        for line in self:
            total_discount = line.l10n_mx_edi_amount_discount * \
                float_round(line.quantity,
                            precision_digits=discount_digits)
            line.l10n_mx_edi_total_discount = total_discount

    def _inverse_total_discount(self):
        deci_pre = self.env['decimal.precision']
        discount_digits = deci_pre.precision_get('Discount')
        for line in self.filtered(lambda l: l.price_unit and l.quantity):
            discount = float_round(
                float_round(line.l10n_mx_edi_total_discount,
                            precision_digits=discount_digits) /
                float_round(line.quantity,
                            precision_digits=discount_digits),
                precision_digits=discount_digits
            )
            line.l10n_mx_edi_amount_discount = discount
            discount = float_round(discount / line.price_unit * 100, precision_digits=discount_digits)
            line.update(line._get_price_total_and_subtotal(discount=discount))

    def _inverse_discount(self):
        deci_pre = self.env['decimal.precision']
        digits = deci_pre.precision_get('Discount')
        for line in self.filtered('price_unit'):
            discount = float_round(
                (float_round(line.l10n_mx_edi_amount_discount,
                             precision_digits=digits) /
                 float_round(line.price_unit,
                             precision_digits=digits)) * 100.00,
                precision_digits=digits
            )
            line.update(line._get_price_total_and_subtotal(discount=discount))


class AccountMove(models.Model):

    _inherit = 'account.move'

    l10n_mx_edi_total_discount = fields.Monetary(
        "Total Discount",
        default=0.0,
        compute='_compute_discount',
        help="Sum of discounts on the invoice.",
    )

    @api.depends('invoice_line_ids')
    def _compute_discount(self):
        for inv in self:
            discount = sum(
                inv.invoice_line_ids.mapped('l10n_mx_edi_total_discount'))
            inv.l10n_mx_edi_total_discount = discount
