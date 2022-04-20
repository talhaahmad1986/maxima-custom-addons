# -*- coding: utf-8 -*-
# This module and its content is copyright of Technaureus Info Solutions Pvt. Ltd.
# - © Technaureus Info Solutions Pvt. Ltd 2021. All rights reserved.

from odoo import fields, models,_
from odoo.exceptions import UserError


class AccountingCommonPartnerReport(models.TransientModel):
    _inherit = 'account.common.partner.report'

    partner_ids = fields.Many2many('res.partner', string='Partners')
    show_initial_balance = fields.Boolean(string='Show Initial Balance')
    show_closing_balance = fields.Boolean(string='Show Closing Balance')

    def pre_print_report(self, data):
        res = super(AccountingCommonPartnerReport, self).pre_print_report(data)
        data['form'].update(self.read(['partner_ids', 'show_initial_balance', 'show_closing_balance'])[0])
        if data['form'].get('show_initial_balance') and not data['form'].get('date_from'):
            raise UserError(_("You must define a Start Date"))
        if data['form'].get('show_closing_balance') and not data['form'].get('show_initial_balance'):
            raise UserError(_("You must enable Show Initial Balance"))
        return res
