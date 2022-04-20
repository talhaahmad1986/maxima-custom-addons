# -*- coding: utf-8 -*-
# This module and its content is copyright of Technaureus Info Solutions Pvt. Ltd.
# - © Technaureus Info Solutions Pvt. Ltd 2021. All rights reserved.

import time
import logging
from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ReportPartnerLedger(models.AbstractModel):
    _inherit = 'report.accounting_pdf_reports.report_partnerledger'

    def _get_init_balance(self, data, partner, init_balance):
        if init_balance:
            query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}),
                                                                        date_to=False, initial_bal=True)._query_get()
            reconcile_clause = "" if data['form'][
                'reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
            params = [partner.id, tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + \
                     query_get_data[2]
            query = """
                        SELECT sum("account_move_line".debit) as debit, sum("account_move_line".credit) as credit,
               sum("account_move_line".debit - "account_move_line".credit) as balance
                        FROM """ + query_get_data[0] + """
                        LEFT JOIN account_journal j ON ("account_move_line".journal_id = j.id)
                        LEFT JOIN account_account acc ON ("account_move_line".account_id = acc.id)
                        LEFT JOIN res_currency c ON ("account_move_line".currency_id=c.id)
                        LEFT JOIN account_move m ON (m.id="account_move_line".move_id)
                        WHERE "account_move_line".partner_id = %s
                            AND m.state IN %s
                            AND "account_move_line".account_id IN %s  AND """ + query_get_data[1] + reconcile_clause + """
                            """
            self.env.cr.execute(query, tuple(params))
            res = self.env.cr.dictfetchall()
            return res

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        data['computed'] = {}

        obj_partner = self.env['res.partner']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        data['computed']['move_state'] = ['draft', 'posted']
        if data['form'].get('target_move', 'all') == 'posted':
            data['computed']['move_state'] = ['posted']
        result_selection = data['form'].get('result_selection', 'customer')
        if result_selection == 'supplier':
            data['computed']['ACCOUNT_TYPE'] = ['payable']
        elif result_selection == 'customer':
            data['computed']['ACCOUNT_TYPE'] = ['receivable']
        else:
            data['computed']['ACCOUNT_TYPE'] = ['payable', 'receivable']

        self.env.cr.execute("""
            SELECT a.id
            FROM account_account a
            WHERE a.internal_type IN %s
            AND NOT a.deprecated""", (tuple(data['computed']['ACCOUNT_TYPE']),))
        data['computed']['account_ids'] = [a for (a,) in self.env.cr.fetchall()]
        params = [tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + query_get_data[2]
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        query = """
            SELECT DISTINCT "account_move_line".partner_id
            FROM """ + query_get_data[0] + """, account_account AS account, account_move AS am
            WHERE "account_move_line".partner_id IS NOT NULL
                AND "account_move_line".account_id = account.id
                AND am.id = "account_move_line".move_id
                AND am.state IN %s
                AND "account_move_line".account_id IN %s
                AND NOT account.deprecated
                AND """ + query_get_data[1] + reconcile_clause
        self.env.cr.execute(query, tuple(params))
        if data['form']['partner_ids']:
            partner_ids = data['form']['partner_ids']
        else:
            partner_ids = [res['partner_id'] for res in self.env.cr.dictfetchall()]
        partners = obj_partner.browse(partner_ids)
        partners = sorted(partners, key=lambda x: (x.ref or '', x.name or ''))
        return {
            'doc_ids': partner_ids,
            'doc_model': self.env['res.partner'],
            'data': data,
            'docs': partners,
            'time': time,
            'lines': self._lines,
            'sum_partner': self._sum_partner,
            '_init_bal': self._get_init_balance,
        }
