# Copyright 2018 Vauxoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def action_create_payments(self):
        if self.payment_difference:
            context = self._context.copy()
            context['payment_difference'] = self.payment_difference
            new_self = self.with_context(context)
            return super(
                AccountPaymentRegister, new_self).action_create_payments()
        return super().action_create_payments()
