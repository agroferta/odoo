from lxml.objectify import fromstring

from odoo.addons.l10n_mx_edi.tests.common import TestMxEdiCommon


class TestL10nMxEdiInvoiceAirline(TestMxEdiCommon):

    def setUp(self):
        super(TestL10nMxEdiInvoiceAirline, self).setUp()
        self.certificate._check_credentials()
        self.tua = self.env['product.product'].create({
            'name': 'TUA',
            'default_code': 'tua',
            'lst_price': '135.00',
            'l10n_mx_edi_airline_type': 'tua',
            'unspsc_code_id': self.ref('product_unspsc.unspsc_code_01010101'),
        })

    def test_invoice_airline_no_extra_charges(self):
        invoice = self.invoice
        invoice.line_ids.unlink()
        invoice.invoice_line_ids.unlink()
        self.tua.taxes_id = False
        invoice.invoice_line_ids = [self.create_airline_line(
            self.tua, invoice.id)]
        invoice.action_post()
        generated_files = self._process_documents_web_services(self.invoice, {'cfdi_3_3'})
        self.assertTrue(generated_files)
        self.assertEqual(invoice.edi_state, "sent", invoice.message_ids.mapped('body'))
        xml = fromstring(generated_files[0])
        namespaces = {
            'aerolineas': 'http://www.sat.gob.mx/aerolineas'}
        comp = xml.Complemento.xpath('//aerolineas:Aerolineas',
                                     namespaces=namespaces)
        self.assertTrue(comp, 'Complement to Airlines not added correctly')

    def test_invoice_airline_extra_charges(self):
        extra_charge1 = self.env['product.product'].create({
            'name': 'Charge DW',
            'default_code': 'DW',
            'lst_price': '220.00',
            'l10n_mx_edi_airline_type': 'extra',
        })
        extra_charge1.unspsc_code_id = self.ref('product_unspsc.unspsc_code_01010101')
        extra_charge1.taxes_id = False
        extra_charge2 = self.env['product.product'].create({
            'name': 'Charge BA',
            'default_code': 'BA',
            'lst_price': '125.00',
            'l10n_mx_edi_airline_type': 'extra',
        })
        extra_charge2.unspsc_code_id = self.ref('product_unspsc.unspsc_code_01010101')
        extra_charge2.taxes_id = False
        invoice = self.invoice
        invoice.line_ids.unlink()
        invoice.invoice_line_ids.unlink()
        lines = [self.create_airline_line(self.tua, invoice.id)]
        lines.append(self.create_airline_line(extra_charge1, invoice.id))
        lines.append(self.create_airline_line(extra_charge2, invoice.id))
        invoice.invoice_line_ids = lines
        invoice.action_post()
        generated_files = self._process_documents_web_services(self.invoice, {'cfdi_3_3'})
        self.assertTrue(generated_files)
        self.assertEqual(invoice.edi_state, "sent", invoice.message_ids.mapped('body'))
        xml = fromstring(generated_files[0])
        namespaces = {
            'aerolineas': 'http://www.sat.gob.mx/aerolineas'}
        comp = xml.Complemento.xpath('//aerolineas:OtrosCargos',
                                     namespaces=namespaces)
        self.assertTrue(comp, 'Complement to Airlines not added correctly')

    def create_airline_line(self, product, move_id):
        move_line = self.env['account.move.line']
        invoice_line = move_line.new({
            'product_id': product.id,
            'quantity': 1,
            'move_id': move_id,
        })
        invoice_line._onchange_product_id()
        invoice_line.move_id = False
        invoice_line_dict = invoice_line._convert_to_write({
            name: invoice_line[name] for name in invoice_line._cache
        })
        invoice_line_dict['price_unit'] = product.lst_price
        invoice_line_dict['tax_ids'] = False
        return (0, 0, invoice_line_dict)
