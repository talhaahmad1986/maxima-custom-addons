# -*- coding: utf-8 -*-
# This module and its content is copyright of Technaureus Info Solutions Pvt. Ltd.
# - © Technaureus Info Solutions Pvt. Ltd 2021. All rights reserved.
{
    'name': 'Partner Ledger Filter with Initial and Closing Balance',
    'version': '15.0.0.0',
    'category': 'Account',
    'sequence': 1,
    'author': 'Technaureus Info Solutions Pvt. Ltd.',
    'summary': 'Partner filter & show initial and closing balance ',
    'description': """

    """,
    'website': 'http://www.technaureus.com',
    'price': 16.99,
    'currency': 'EUR',
    'license': 'Other proprietary',
    'depends': [
        'accounting_pdf_reports'
	],
    'data': [
        'wizard/account_report_partner_ledger_view.xml',
        'report/report_partnerledger.xml'
    ],
    'installable': True,
    'application': True,
    'images': ['images/main_screenshot.png'],
    'live_test_url': 'https://www.youtube.com/watch?v=0a4QVuSHh1M'
}
