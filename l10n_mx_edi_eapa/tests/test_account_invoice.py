from lxml.objectify import fromstring

from odoo.addons.l10n_mx_edi.tests.common import TestMxEdiCommon


class TestL10nMxEdiInvoiceEAPA(TestMxEdiCommon):

    def test_l10n_mx_edi_invoice_eapa(self):
        self.product.write({
            'l10n_mx_edi_art_complement': 'eapa',
            'l10n_mx_edi_good_type': '03',
            'l10n_mx_edi_acquisition': '05',
            'l10n_mx_edi_other_good_type': 'Was found in a construction',
            'l10n_mx_edi_tax_paid': '15.00',
            'l10n_mx_edi_acquisition_date': '2015/07/01',
            'l10n_mx_edi_characteristic': '06',
            'standard_price': 1000,
        })
        invoice = self.invoice
        invoice.action_post()
        generated_files = self._process_documents_web_services(self.invoice, {'cfdi_3_3'})
        self.assertTrue(generated_files)
        self.assertEqual(invoice.edi_state, "sent", invoice.message_ids.mapped('body'))
        xml = fromstring(generated_files[0])
        namespaces = {
            'obrasarte': 'http://www.sat.gob.mx/arteantiguedades'}
        eapa = xml.Complemento.xpath('//obrasarte:obrasarteantiguedades',
                                     namespaces=namespaces)
        self.assertTrue(eapa, 'Complement to EAPA not added correctly')

    def test_l10n_mx_edi_xsd(self):
        """Verify that xsd file is downloaded"""
        self.invoice.company_id._load_xsd_attachments()
        xsd_file = self.ref(
            'l10n_mx_edi.xsd_cached_obrasarteantiguedades_xsd')
        self.assertTrue(xsd_file, 'XSD file not load')

    def test_invoice_payment_in_kind(self):
        self.donation = self.env['product.product'].create({
            'name': 'Painting',
            'lst_price': '1.00',
            'l10n_mx_edi_art_complement': 'pee',
            'l10n_mx_edi_good_type': '04',
            'l10n_mx_edi_other_good_type': 'oil painting',
            'l10n_mx_edi_acquisition_date': '2000/01/19',
            'l10n_mx_edi_pik_dimension': '2m height and 2m width',
        })
        self.donation.unspsc_code_id = self.ref('product_unspsc.unspsc_code_01010101')
        self.donation.taxes_id.unlink()

        invoice = self.invoice
        invoice.sudo().partner_id.ref = 'A&C8317286A1-18000101-020'
        invoice.name = 'PE-53-78436'
        self.create_donation_line(invoice, self.donation)
        invoice.message_ids.unlink()
        invoice.action_post()
        generated_files = self._process_documents_web_services(self.invoice, {'cfdi_3_3'})
        self.assertTrue(generated_files)
        self.assertEqual(invoice.edi_state, "sent", invoice.message_ids.mapped('body'))
        xml = fromstring(generated_files[0])
        xml_expected = fromstring(
            '<pagoenespecie:PagoEnEspecie '
            'xmlns:pagoenespecie="http://www.sat.gob.mx/pagoenespecie" '
            'Version="1.0" CvePIC="A&amp;C8317286A1-18000101-020" '
            'FolioSolDon="PE-53-78436" PzaArtNombre="Painting" '
            'PzaArtTecn="oil painting" PzaArtAProd="2000" '
            'PzaArtDim="2m height and 2m width"/>')
        namespaces = {
            'pagoenespecie': 'http://www.sat.gob.mx/pagoenespecie'}
        comp = xml.Complemento.xpath('//pagoenespecie:PagoEnEspecie',
                                     namespaces=namespaces)
        self.assertEqualXML(comp[0], xml_expected)

    def create_donation_line(self, invoice, product):
        invoice_line = self.invoice_line_model.new({
            'product_id': product.id,
            'invoice_id': invoice,
            'quantity': 1,
        })
        invoice_line._onchange_product_id()
        invoice_line_dict = invoice_line._convert_to_write({
            name: invoice_line[name] for name in invoice_line._cache
        })
        invoice_line_dict['price_unit'] = product.lst_price
        self.invoice_line_model.create(invoice_line_dict)
