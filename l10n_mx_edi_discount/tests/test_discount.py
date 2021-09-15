import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestDiscount(TransactionCase):

    def setUp(self):
        super(TestDiscount, self).setUp()
        self.invoice_model = self.env['account.move']
        self.invoice_line_model = self.env['account.move.line']
        self.partner_a = self.env.ref("base.res_partner_address_4")
        self.mxn = self.env.ref('base.MXN')
        self.product = self.env.ref("product.product_product_3")

    def test_01(self):

        dp = self.env['decimal.precision']

        dp_discount = self.env.ref('product.decimal_discount')
        dp_discount.digits = 4

        dp_price = self.env.ref('product.decimal_price')
        dp_price.digits = 4

        self.assertEqual(dp_discount.digits, dp.precision_get('Discount'))
        self.assertEqual(dp_price.digits, dp.precision_get('Product Price'))

        invoice = self.invoice_model.new({
            'name': 'INV/0003',
            'partner_id': self.partner_a.id,
            'move_type': 'out_invoice',
            'currency_id': self.mxn.id,
        })

        user_type = self.env.ref('account.data_account_type_revenue')
        account = self.env['account.account'].search(
            [('user_type_id', '=', user_type.id),
             ('company_id', '=', invoice.company_id.id)], limit=1)

        invoice.invoice_line_ids = ([(0, 0, {
            'name': 'Product 001',
            'product_id': self.product.id,
            'quantity': 1.0,
            'price_unit': 16.40,
            'account_id': account.id,
            'l10n_mx_edi_total_discount': 0.5,
        }), (0, 0, {
            'name': 'Product 002',
            'product_id': self.product.id,
            'quantity': 4.0,
            'price_unit': 11.73,
            'account_id': account.id,
            'l10n_mx_edi_total_discount': 1.41,
        })])
        invoice._compute_discount()
        invoice_dict = self.invoice_model._convert_to_write(invoice._cache)
        invoice_dict.update({'line_ids': False})
        self.assertEqual(
            round(invoice_dict['l10n_mx_edi_total_discount'],
                  dp.precision_get('Discount')), 1.91)

    def test_02_compute_discount(self):
        dp = self.env['decimal.precision']
        discount_digits = dp.precision_get('Discount')
        invoice = self.invoice_model.create({
            'name': 'INV/0009',
            'partner_id': self.partner_a.id,
            'move_type': 'out_invoice',
            'currency_id': self.mxn.id,
        })
        user_type = self.env.ref('account.data_account_type_revenue')
        account = self.env['account.account'].search(
            [('user_type_id', '=', user_type.id),
             ('company_id', '=', invoice.company_id.id)], limit=1)
        invoice.invoice_line_ids = ([(0, 0, {
            'name': 'CFPE1IWY',
            'product_id': self.product.id,
            'quantity': 89.0000,
            'price_unit': 42.0000,
            'discount': 4.9998,
            'account_id': account.id,
        }), (0, 0, {
            'name': 'CFPE1WHY',
            'product_id': self.product.id,
            'quantity': 20.0000,
            'price_unit': 42.0000,
            'discount': 5.0071,
            'account_id': account.id,
        }), (0, 0, {
            'name': 'CFPE2IWY',
            'product_id': self.product.id,
            'quantity': 20.0000,
            'price_unit': 42.0000,
            'discount': 5.0071,
            'account_id': account.id,
        }), (0, 0, {
            'name': 'CJ688TGBL',
            'product_id': self.product.id,
            'quantity': 30.0000,
            'price_unit': 168.9400,
            'discount': 4.9994,
            'account_id': account.id,
        }), (0, 0, {
            'name': 'CJ688TGIW',
            'product_id': self.product.id,
            'quantity': 30.0000,
            'price_unit': 168.9400,
            'discount': 4.9994,
            'account_id': account.id,
        }), (0, 0, {
            'name': 'FOWNX06',
            'product_id': self.product.id,
            'quantity': 821.0000,
            'price_unit': 15.2800,
            'discount': 4.9993,
            'account_id': account.id,
        }), (0, 0, {
            'name': 'UTPSP7Y',
            'product_id': self.product.id,
            'quantity': 30.0000,
            'price_unit': 167.2800,
            'discount': 4.9988,
            'account_id': account.id,
        })])
        invoice._compute_discount()
        self.assertEqual(
            round(invoice.l10n_mx_edi_total_discount, discount_digits),
            1652.66)
