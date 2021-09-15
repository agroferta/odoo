
from lxml.objectify import fromstring
from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_mx_edi_decode_cfdi(self, cfdi_data=None):
        """If the CFDI was signed, try to adds the schemaLocation correctly"""
        result = super(AccountMove, self)._l10n_mx_edi_decode_cfdi(cfdi_data=cfdi_data)
        if not cfdi_data:
            return result
        cfdi_data = cfdi_data.replace(b'xmlns__aerolineas', b'xmlns:aerolineas')
        cfdi = fromstring(cfdi_data)
        if 'aerolineas' not in cfdi.nsmap:
            return result
        cfdi.attrib['{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'] = '%s %s %s' % (
            cfdi.get('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'),
            'http://www.sat.gob.mx/aerolineas',
            'http://www.sat.gob.mx/sitio_internet/cfd/aerolineas/aerolineas.xsd')
        result['cfdi_node'] = cfdi
        return result
