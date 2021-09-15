from lxml import objectify

from odoo.addons.l10n_mx_edi.tests.common import TestMxEdiCommon


class TestFiscalLegend(TestMxEdiCommon):
    def test_xml_node(self):
        """Validates that the XML node ``<leyendasFisc:LeyendasFiscales>`` is
            included when the invoice contains fiscal legends, and that
            its content is generated correctly
        """
        self.certificate._check_credentials()
        self.namespaces = {
            'cfdi': 'http://www.sat.gob.mx/cfd/3',
            'leyendasFisc': 'http://www.sat.gob.mx/leyendasFiscales',
        }
        self.legend = self.env['l10n_mx_edi.fiscal.legend'].create({
            'name': "Legend's Text",
            'tax_provision': 'ISR',
            'rule': 'Article 1, paragraph 2',
        })

        xml_expected = objectify.fromstring('''
            <leyendasFisc:LeyendasFiscales
                xmlns:leyendasFisc="http://www.sat.gob.mx/leyendasFiscales"
                version="1.0">
                <leyendasFisc:Leyenda
                    disposicionFiscal="ISR"
                    norma="Article 1, paragraph 2"
                    textoLeyenda="Legend's Text"/>
            </leyendasFisc:LeyendasFiscales>''')
        invoice = self.invoice
        invoice.l10n_mx_edi_legend_ids = self.legend
        invoice.action_post()
        generated_files = self._process_documents_web_services(self.invoice, {'cfdi_3_3'})
        self.assertTrue(generated_files)
        self.assertEqual(invoice.edi_state, "sent", invoice.message_ids.mapped('body'))
        xml = objectify.fromstring(generated_files[0])
        self.assertTrue(xml.Complemento.xpath(
            'leyendasFisc:LeyendasFiscales', namespaces=self.namespaces),
            "The node '<leyendasFisc:LeyendasFiscales> should be present")
        xml_leyendas = xml.Complemento.xpath(
            'leyendasFisc:LeyendasFiscales', namespaces=self.namespaces)[0]
        self.assertEqualXML(xml_leyendas, xml_expected)

    def xml2dict(self, xml):
        """Receive 1 lxml etree object and return a dict string.
        This method allow us have a precise diff output"""
        def recursive_dict(element):
            return (element.tag,
                    dict((recursive_dict(e) for e in element.getchildren()),
                         ____text=(element.text or '').strip(), **element.attrib))
        return dict([recursive_dict(xml)])

    def assertEqualXML(self, xml_real, xml_expected):  # pylint: disable=invalid-name
        """Receive 2 objectify objects and show a diff assert if exists."""
        xml_expected = self.xml2dict(xml_expected)
        xml_real = self.xml2dict(xml_real)
        # "self.maxDiff = None" is used to get a full diff from assertEqual method
        # This allow us get a precise and large log message of where is failing
        # expected xml vs real xml More info:
        # https://docs.python.org/2/library/unittest.html#unittest.TestCase.maxDiff
        self.maxDiff = None
        self.assertEqual(xml_real, xml_expected)
