# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2021-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import fields, models


class AccountPartnerLedger(models.TransientModel):
    _inherit = "account.report.partner.ledger"

    partner_ids = fields.Many2many('res.partner', 'partner_ledger_partner_rel', 'id', 'partner_id', string='Partners')

    def _print_report(self, data):
        data = {
            'ids': self.ids,
            'model': 'account.report.partner.ledger',
            'form': self.read()[0],
        }
        groupby = []
        vals = {}
        info = [ ]
        counter = 0
        for partner in self.partner_ids:
            entries = self.env['account.move.line'].search([('date', '>=', self.date_from), ('date', '<=', self.date_to), ('partner_id', '=', partner.id)], order='date ASC')
            for line in entries:
                balance = line.balance
                partner_name = line.partner_id.name
                if partner_name not in vals and partner_name not in groupby:
                    groupby.append(partner_name)
                    counter += 1
                    vals.update({
                        partner_name: [{
                            'sn_no': counter ,
                            'date': line.date,
                            'sl_no': line.move_name,
                            'ref_no': '',
                            'et': 'SI',
                            'remarks': line.move_id.ref,
                            'debit': line.debit,
                            'credit': line.credit,
                            'balance': balance + (line.debit - line.credit)

                        }]
                    })
                else:
                    if partner_name not in groupby:
                        groupby.append(partner_name)
                    new_dict = {
                        'sn_no': counter,
                        'date': line.date,
                        'sl_no': line.move_name,
                        'ref_no': '',
                        'et': 'SI',
                        'remarks': line.move_id.ref,
                        'debit': line.debit,
                        'credit': line.credit,
                        'balance': balance + (line.debit - line.credit)

                    }
                    row = vals.get(partner_name)
                    row.append(new_dict)
        filter = {

            'from': self.from_date,
            'to': self.to_date,
        }
        info.append(filter)
        data['filters'] = filter
        data['members'] = vals
        data['groupby'] = groupby
        print()
        return self.env.ref('base_accounting_kit.action_report_partnerledger').report_action(self, data=data)

