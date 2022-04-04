# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2019 EquickERP
#
##############################################################################
{
    'name': "Invoice From Picking (Talha Ahmad)",
    'category': 'Accounting',
    'version': '15.0.29.01.22',
    'author': 'Equick ERP',
    'description': """
        This Module allows you to create invoice from picking.
        * Allows you to create customer/vendor invoices from Picking (Delivery Order/ Incoming Shipment).
        * Allows you to create invoice by partner wise.
        * Link invoice to Sale/Purchase order respectively.
        ----------------------------------------------
        * Date : 12-january-2022
        change for create the invoice/bill without sales/purchase order from picking.
        ----------------------------------------------
        * Date : 29-january-2022
        add field on the stock.move for the price and that field will use for the create picking.
    """,
    'summary': """Invoice from delivery order | Invoice from incoming shipment | customer invoice from delivery order | vendor bill from incoming shipment  bill from receipt | generate invoice from picking | generate bill from picking.""",
    'depends': ['base', 'sale_management', 'stock', 'purchase'],
    'price': 25,
    'currency': 'EUR',
    'license': 'OPL-1',
    'website': "",
    'data': [
        'security/ir.model.access.csv',
        'views/stock_view.xml',
    ],
    'demo': [],
    'images': ['static/description/main_screenshot.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: