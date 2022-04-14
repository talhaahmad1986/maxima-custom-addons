# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2019 EquickERP
#
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

journal_type_dict = {
    ('outgoing', 'customer'): ['out_invoice'],
    ('incoming', 'supplier'): ['in_invoice'],
    ('incoming', 'customer'): ['out_refund'],
    ('outgoing', 'supplier'): ['in_refund']
}


class stock_picking(models.Model):
    _inherit = 'stock.picking'

    @api.depends('invoice_ids')
    def _get_len_invoice_ids(self):
        for picking in self:
            picking.invoice_ids_count = len(picking.invoice_ids)

    invoice_ids = fields.Many2many('account.move', 'table_account_invoice_stock_picking_relation', 'picking_id',
                                   'invoice_id',
                                   string="Invoice", copy=False)
    invoice_ids_count = fields.Integer(string="Invoices", compute="_get_len_invoice_ids", store=True)
    del_add = fields.Char('Delivery Address')
    lpo = fields.Char('LPO Number')
    inv_ref = fields.Char('Invoice Ref')
    mark = fields.Char('Mark')
    driver = fields.Char('Driver name')
    vehicle = fields.Char('Vehicle number')
    stock_location = fields.Many2one('stock.location', string="Stock Location")
    keeper = fields.Char('Store Keeper')
    loadby = fields.Char('Loaded by')

    def view_account_invoices(self):
        if self.invoice_ids:
            invoice_type = self.invoice_ids[0].move_type
            if invoice_type == 'in_invoice':
                action = self.env.ref('account.action_move_in_invoice_type').read()[0]
            else:  # invoice_type == 'out_invoice':
                action = self.env.ref('account.action_move_out_invoice_type').read()[0]
            action['domain'] = [('id', 'in', self.invoice_ids.ids)]
            return action

    def _prepare_invoice(self):
        self.ensure_one()
        context = self.env.context
        invoice_vals = {
            'move_type': context.get('invoice_type'),
            'partner_id': self.partner_id.id,
            'journal_id': context.get('journal_id'),
            'company_id': self.company_id.id,
            'invoice_date': context.get('invoice_date'),
            'stock_picking_ids': [(4, self.id)],
            'user_id': context.get('user_id'),
            'invoice_origin': self.name
        }
        return invoice_vals

    def button_validate(self):
        # Clean-up the context key at validation to avoid forcing the creation of immediate
        # transfers.
        gr = self.write_uid.groups_id.filtered(lambda a: a.name == 'Move Confirmation')
        if gr:
            ctx = dict(self.env.context)
            ctx.pop('default_immediate_transfer', None)
            self = self.with_context(ctx)

            # Sanity checks.
            pickings_without_moves = self.browse()
            pickings_without_quantities = self.browse()
            pickings_without_lots = self.browse()
            products_without_lots = self.env['product.product']
            for picking in self:
                if not picking.move_lines and not picking.move_line_ids:
                    pickings_without_moves |= picking

                picking.message_subscribe([self.env.user.partner_id.id])
                picking_type = picking.picking_type_id
                precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
                no_quantities_done = all(
                    float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in
                    picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
                no_reserved_quantities = all(
                    float_is_zero(move_line.product_qty, precision_rounding=move_line.product_uom_id.rounding) for
                    move_line in picking.move_line_ids)
                if no_reserved_quantities and no_quantities_done:
                    pickings_without_quantities |= picking

                if picking_type.use_create_lots or picking_type.use_existing_lots:
                    lines_to_check = picking.move_line_ids
                    if not no_quantities_done:
                        lines_to_check = lines_to_check.filtered(lambda line: float_compare(line.qty_done, 0,
                                                                                            precision_rounding=line.product_uom_id.rounding))
                    for line in lines_to_check:
                        product = line.product_id
                        if product and product.tracking != 'none':
                            if not line.lot_name and not line.lot_id:
                                pickings_without_lots |= picking
                                products_without_lots |= product

            if not self._should_show_transfers():
                if pickings_without_moves:
                    raise UserError(_('Please add some items to move.'))
                if pickings_without_quantities:
                    raise UserError(self._get_without_quantities_error_message())
                if pickings_without_lots:
                    raise UserError(_('You need to supply a Lot/Serial number for products %s.') % ', '.join(
                        products_without_lots.mapped('display_name')))
            else:
                message = ""
                if pickings_without_moves:
                    message += _('Transfers %s: Please add some items to move.') % ', '.join(
                        pickings_without_moves.mapped('name'))
                if pickings_without_quantities:
                    message += _(
                        '\n\nTransfers %s: You cannot validate these transfers if no quantities are reserved nor done. To force these transfers, switch in edit more and encode the done quantities.') % ', '.join(
                        pickings_without_quantities.mapped('name'))
                if pickings_without_lots:
                    message += _('\n\nTransfers %s: You need to supply a Lot/Serial number for products %s.') % (
                        ', '.join(pickings_without_lots.mapped('name')),
                        ', '.join(products_without_lots.mapped('display_name')))
                if message:
                    raise UserError(message.lstrip())

            # Run the pre-validation wizards. Processing a pre-validation wizard should work on the
            # moves and/or the context and never call `_action_done`.
            if not self.env.context.get('button_validate_picking_ids'):
                self = self.with_context(button_validate_picking_ids=self.ids)
            res = self._pre_action_done_hook()
            if res is not True:
                return res

            # Call `_action_done`.
            if self.env.context.get('picking_ids_not_to_backorder'):
                pickings_not_to_backorder = self.browse(self.env.context['picking_ids_not_to_backorder'])
                pickings_to_backorder = self - pickings_not_to_backorder
            else:
                pickings_not_to_backorder = self.env['stock.picking']
                pickings_to_backorder = self
            pickings_not_to_backorder.with_context(cancel_backorder=True)._action_done()
            pickings_to_backorder.with_context(cancel_backorder=False)._action_done()

            if self.user_has_groups('stock.group_reception_report') \
                    and self.user_has_groups('stock.group_auto_reception_report') \
                    and self.filtered(lambda p: p.picking_type_id.code != 'outgoing'):
                lines = self.move_lines.filtered(lambda
                                                     m: m.product_id.type == 'product' and m.state != 'cancel' and m.quantity_done and not m.move_dest_ids)
                if lines:
                    # don't show reception report if all already assigned/nothing to assign
                    wh_location_ids = self.env['stock.location'].search(
                        [('id', 'child_of', self.picking_type_id.warehouse_id.view_location_id.id),
                         ('location_id.usage', '!=', 'supplier')]).ids
                    if self.env['stock.move'].search([
                        ('state', 'in', ['confirmed', 'partially_available', 'waiting', 'assigned']),
                        ('product_qty', '>', 0),
                        ('location_id', 'in', wh_location_ids),
                        ('move_orig_ids', '=', False),
                        ('picking_id', 'not in', self.ids),
                        ('product_id', 'in', lines.product_id.ids)], limit=1):
                        action = self.action_view_reception_report()
                        action['context'] = {'default_picking_ids': self.ids}
                        return action
            return True
        else:
            raise ValidationError(_(
                "You are not allow to perform this operation. "
            ))


class account_move(models.Model):
    _inherit = 'account.move'

    def _prepare_invoice_line_from_po_line(self, line):
        data = super(account_move, self)._prepare_invoice_line_from_po_line(line)
        if self.env.context.get('from_picking_done_qty'):
            data['quantity'] = self.env.context.get('from_picking_done_qty')
        return data

    stock_picking_ids = fields.Many2many('stock.picking', 'table_account_invoice_stock_picking_relation', 'invoice_id',
                                         'picking_id',
                                         string="Picking Ref.")


class wizard_stock_picking_invoice(models.TransientModel):
    _name = 'wizard.stock.picking.invoice'
    _description = "Wizard Stock Picking Description"

    journal_id = fields.Many2one('account.journal', string="Journal", required=True)
    invoice_type = fields.Selection([('out_invoice', 'Create Customer Invoice'),
                                     ('out_refund', 'Create Customer Credit Note'),
                                     ('in_invoice', 'Create Vendor Bill'),
                                     ('in_refund', 'Create Vendor Refund')], 'Invoice Type', readonly=True)
    invoice_date = fields.Date(string="Invoice Date")
    group_by_partner = fields.Boolean(string="Group By Partner")

    @api.model
    def default_get(self, fieldslist):
        res = super(wizard_stock_picking_invoice, self).default_get(fieldslist)
        context = self.env.context
        picking_ids = context and context.get('active_ids', [])
        pickings = self.env['stock.picking'].browse(picking_ids)
        pick = pickings and pickings[0]
        if not pick or not pick.move_lines:
            return {}
        type = pick.picking_type_code
        usage = pick.move_lines[0].location_id.usage if type == 'incoming' else pick.move_lines[
            0].location_dest_id.usage
        res.update({'invoice_type': journal_type_dict.get((type, usage), [''])[0]})
        return res

    @api.onchange('invoice_type')
    def _onchange_invoice_type(self):
        domain = [('type', 'in', {'out_invoice': ['sale'],
                                  'out_refund': ['sale'],
                                  'in_refund': ['purchase'],
                                  'in_invoice': ['purchase']}.get(self.invoice_type, [])),
                  ('company_id', '=', self.env.user.company_id.id)]
        return {'domain': {'journal_id': domain}}

    def create_invoice(self):
        picking_ids = self.env['stock.picking'].browse(self.env.context.get('active_ids'))
        invoice_date = self.invoice_date or datetime.now().today().date()
        if any([not picking.partner_id for picking in picking_ids]):
            raise ValidationError(_("Partner not found. For create invoice, into picking must have the partner."))
        picking_code_lst = picking_ids.mapped('picking_type_code')
        if 'internal' in picking_code_lst:
            raise ValidationError(_("Select only Delivery Orders / Receipts for create Invoice."))
        if len(set(picking_code_lst)) > 1:
            raise ValidationError(_("Selected picking must have same Operation Type."))
        if not self.journal_id:
            raise UserError(_('Please define an accounting sales journal for this company.'))

        if any([picking.state not in ['done'] for picking in picking_ids]):
            raise ValidationError(_("Selected picking must have in Done State."))

        groupby_lst = {}
        for picking_id in picking_ids.filtered(lambda l: l.state == 'done'):
            if picking_id.invoice_ids or not picking_id.move_lines:
                continue
            if self.group_by_partner:
                key = picking_id.partner_id.id
            else:
                key = picking_id.id
            groupby_lst.setdefault(key, [])
            groupby_lst[key].append(picking_id)
        new_invoices = self.env['account.move']
        for lst_items in groupby_lst.values():
            invoice_lst = {}
            for picking in lst_items:
                user_id = False
                if picking.sale_id:
                    user_id = picking.sale_id.user_id.id or False
                if picking.purchase_id:
                    user_id = picking.purchase_id.user_id.id or False
                key = (picking.partner_id.id, picking.company_id.id, user_id)
                invoice_vals = picking.with_context(journal_id=self.journal_id.id, invoice_date=self.invoice_date,
                                                    invoice_type=self.invoice_type, user_id=user_id)._prepare_invoice()
                if key not in invoice_lst:
                    invoice_id = self.env['account.move'].with_context(default_type=self.invoice_type).create(
                        invoice_vals)
                    self.set_values(invoice_id)
                    invoice_lst[key] = invoice_id
                    new_invoices += invoice_id
                else:
                    invoice_id = invoice_lst[key]
                    update_inv_data = {'stock_picking_ids': [(4, picking.id)]}
                    if not invoice_id.invoice_origin or invoice_vals[
                        'invoice_origin'] not in invoice_id.invoice_origin.split(', '):
                        invoice_origin = filter(None, [invoice_id.invoice_origin, invoice_vals['invoice_origin']])
                        update_inv_data['invoice_origin'] = ', '.join(invoice_origin)
                    if invoice_vals.get('name', False) and (
                            not invoice_id.name or invoice_vals['name'] not in invoice_id.name.split(', ')):
                        invoice_name = filter(None, [invoice_id.name, invoice_vals['name']])
                        update_inv_data['name'] = ', '.join(invoice_name)
                    if update_inv_data:
                        invoice_id.write(update_inv_data)
                if invoice_id:
                    inv_line_vals = []
                    for each in picking.move_lines:
                        if each.sale_line_id and each.sale_line_id.qty_to_invoice > 0:
                            qty = each.sale_line_id.qty_to_invoice
                            if qty > each.quantity_done:
                                qty = each.quantity_done
                            prepare_invoice_line_vals = each.sale_line_id._prepare_invoice_line()
                            prepare_invoice_line_vals.update({'quantity': qty})
                            inv_line_vals.append((0, 0, prepare_invoice_line_vals))
                        if each.purchase_line_id:
                            qty = each.purchase_line_id.product_qty - each.purchase_line_id.qty_invoiced
                            if qty > each.quantity_done:
                                qty = each.quantity_done
                            if each.quantity_done > each.purchase_line_id.product_qty:
                                qty = each.quantity_done
                            if qty > 0:
                                invoice_id.write({'purchase_id': each.purchase_line_id.order_id.id})
                                prepare_invoice_line_vals = each.purchase_line_id._prepare_account_move_line(invoice_id)
                                prepare_invoice_line_vals.update({'quantity': qty})
                                inv_line_vals.append((0, 0, prepare_invoice_line_vals))

                        if (not each.sale_line_id) and (not each.purchase_line_id):
                            prod_id = each.product_id
                            prepare_invoice_line_vals = {'name': '%s' % (each.name),
                                                         'move_id': invoice_id.id,
                                                         'currency_id': invoice_id.currency_id.id,
                                                         'date_maturity': invoice_id.invoice_date_due,
                                                         'product_uom_id': each.product_uom.id,
                                                         'product_id': prod_id.id,
                                                         'quantity': each.quantity_done,
                                                         'partner_id': invoice_id.partner_id.id}
                            if invoice_id.move_type in ['in_invoice', 'in_refund']:
                                prod_buy_price = prod_id.standard_price
                                prepare_invoice_line_vals.update({'price_unit': prod_buy_price,
                                                                  'tax_ids': [(6, 0, prod_id.supplier_taxes_id.ids)], })
                            elif invoice_id.move_type in ['out_invoice', 'out_refund']:
                                prod_sale_price = prod_id.list_price
                                move_fields = self.env['stock.move']._fields.keys()
                                if 'price' in move_fields:
                                    prod_sale_price = each.price
                                prepare_invoice_line_vals.update({'price_unit': prod_sale_price,
                                                                  'tax_ids': [(6, 0, prod_id.taxes_id.ids)], })
                            # for the invoice with different type of picking like return
                            #                             picking_return_qty_for_inv = self.get_new_return_qty(picking, prepare_invoice_line_vals['quantity'])
                            #                             prepare_invoice_line_vals.update({'quantity': picking_return_qty_for_inv})

                            inv_line_vals.append((0, 0, prepare_invoice_line_vals))

                    if inv_line_vals:
                        invoice_id.write({'invoice_line_ids': inv_line_vals})
                    picking.write({'invoice_ids': [(4, invoice_id.id)],
                                   })
        for eachinv in new_invoices:
            eachinv._compute_amount()
            if not eachinv.invoice_line_ids:
                eachinv.sudo().unlink()

    def set_values(self, invoice_id):
        picking_ids = self.env['stock.picking'].browse(self.env.context.get('active_ids'))
        invoice_id.lpo = picking_ids.lpo
        invoice_id.del_add = picking_ids.del_add
        invoice_id.mark = picking_ids.mark
        invoice_id.do_ref = picking_ids.name


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    price_unit = fields.Float(string='Unit Price', digits='Product Price', compute='check_price',store=True,readonly=False)

    def check_price(self):
        if self.env.context.get('active_model') == 'stock.picking':
            picking = self.env['stock.picking'].browse(self.env.context.get('active_id'))
            for line in picking.move_ids_without_package:
                self.price_unit = float(line.price)
        else:
            for rec in self:
                rec.price_unit = rec.price_unit

    def _get_price_total_and_subtotal(self, price_unit=None, quantity=None, discount=None, currency=None, product=None, partner=None, taxes=None, move_type=None):
        self.ensure_one()
        if self.env.context.get('active_model') == 'stock.picking' and self.price_unit == 0.0:
            self.price_unit = self.check_price()
        return self._get_price_total_and_subtotal_model(
            price_unit=price_unit or self.price_unit ,
            quantity=quantity or self.quantity,
            discount=discount or self.discount,
            currency=currency or self.currency_id,
            product=product or self.product_id,
            partner=partner or self.partner_id,
            taxes=taxes or self.tax_ids,
            move_type=move_type or self.move_id.move_type,
        )

    @api.model
    def _get_price_total_and_subtotal_model(self, price_unit, quantity, discount, currency, product, partner, taxes,
                                            move_type):
        ''' This method is used to compute 'price_total' & 'price_subtotal'.

        :param price_unit:  The current price unit.
        :param quantity:    The current quantity.
        :param discount:    The current discount.
        :param currency:    The line's currency.
        :param product:     The line's product.
        :param partner:     The line's partner.
        :param taxes:       The applied taxes.
        :param move_type:   The type of the move.
        :return:            A dictionary containing 'price_subtotal' & 'price_total'.
        '''
        res = {}

        # Compute 'price_subtotal'.
        line_discount_price_unit = price_unit * (1 - (discount / 100.0))
        subtotal = quantity * line_discount_price_unit

        # Compute 'price_total'.
        if taxes:
            taxes_res = taxes._origin.with_context(force_sign=1).compute_all(line_discount_price_unit,
                                                                             quantity=quantity, currency=currency,
                                                                             product=product, partner=partner,
                                                                             is_refund=move_type in (
                                                                             'out_refund', 'in_refund'))
            res['price_subtotal'] = taxes_res['total_excluded']
            res['price_total'] = taxes_res['total_included']
        else:
            res['price_total'] = res['price_subtotal'] = subtotal
        # In case of multi currency, round before it's use for computing debit credit
        if currency:
            res = {k: currency.round(v) for k, v in res.items()}
        return res

    def _get_fields_onchange_balance(self, quantity=None, discount=None, amount_currency=None, move_type=None,
                                     currency=None, taxes=None, price_subtotal=None, force_computation=False):
        self.ensure_one()
        return self._get_fields_onchange_balance_model(
            quantity=quantity or self.quantity,
            discount=discount or self.discount,
            amount_currency=amount_currency or self.amount_currency,
            move_type=move_type or self.move_id.move_type,
            currency=currency or self.currency_id or self.move_id.currency_id,
            taxes=taxes or self.tax_ids,
            price_subtotal=price_subtotal or self.price_subtotal,
            force_computation=force_computation,
        )

    @api.depends('move_id.move_type', 'tax_ids', 'tax_repartition_line_id', 'debit', 'credit', 'tax_tag_ids')
    def _compute_tax_tag_invert(self):
        for record in self:
            if not record.tax_repartition_line_id and not record.tax_ids:
                # Invoices imported from other softwares might only have kept the tags, not the taxes.
                record.tax_tag_invert = record.tax_tag_ids and record.move_id.is_inbound()

            elif record.move_id.move_type == 'entry':
                # For misc operations, cash basis entries and write-offs from the bank reconciliation widget
                rep_line = record.tax_repartition_line_id
                if rep_line:
                    tax_type = (rep_line.refund_tax_id or rep_line.invoice_tax_id).type_tax_use
                    is_refund = bool(rep_line.refund_tax_id)
                elif record.tax_ids:
                    tax_type = record.tax_ids[0].type_tax_use
                    is_refund = (tax_type == 'sale' and record.debit) or (tax_type == 'purchase' and record.credit)

                record.tax_tag_invert = (tax_type == 'purchase' and is_refund) or (tax_type == 'sale' and not is_refund)

            else:
                # For invoices with taxes
                record.tax_tag_invert = record.move_id.is_inbound()
        # if self.env.context.get('active_model') == 'stock.picking':
        #     picking_id = self.env['stock.picking'].browse(self.env.context.get('active_id'))
        #     for record in self:
        #         for move in picking_id.move_line_ids:
        #             record.price_unit = float(move.move_id.price)
        #             # record.price_subtotal = record.price_unit * record.quantity

    @api.model_create_multi
    def create(self, vals_list):
        # OVERRIDE
        ACCOUNTING_FIELDS = ('debit', 'credit', 'amount_currency')
        BUSINESS_FIELDS = ('price_unit', 'quantity', 'discount', 'tax_ids')

        for vals in vals_list:
            move = self.env['account.move'].browse(vals['move_id'])
            vals.setdefault('company_currency_id',
                            move.company_id.currency_id.id)  # important to bypass the ORM limitation where monetary fields are not rounded; more info in the commit message

            # Ensure balance == amount_currency in case of missing currency or same currency as the one from the
            # company.
            currency_id = vals.get('currency_id') or move.company_id.currency_id.id
            if currency_id == move.company_id.currency_id.id:
                balance = vals.get('debit', 0.0) - vals.get('credit', 0.0)
                vals.update({
                    'currency_id': currency_id,
                    'amount_currency': balance,
                })
            else:
                vals['amount_currency'] = vals.get('amount_currency', 0.0)

            if move.is_invoice(include_receipts=True):
                currency = move.currency_id
                partner = self.env['res.partner'].browse(vals.get('partner_id'))
                taxes = self.new({'tax_ids': vals.get('tax_ids', [])}).tax_ids
                tax_ids = set(taxes.ids)
                taxes = self.env['account.tax'].browse(tax_ids)

                # Ensure consistency between accounting & business fields.
                # As we can't express such synchronization as computed fields without cycling, we need to do it both
                # in onchange and in create/write. So, if something changed in accounting [resp. business] fields,
                # business [resp. accounting] fields are recomputed.
                if any(vals.get(field) for field in ACCOUNTING_FIELDS):
                    price_subtotal = self._get_price_total_and_subtotal_model(
                        vals.get('price_unit', 0.0),
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        currency,
                        self.env['product.product'].browse(vals.get('product_id')),
                        partner,
                        taxes,
                        move.move_type,
                    ).get('price_subtotal', 0.0)
                    vals.update(self._get_fields_onchange_balance_model(
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        vals['amount_currency'],
                        move.move_type,
                        currency,
                        taxes,
                        price_subtotal
                    ))
                    vals.update(self._get_price_total_and_subtotal_model(
                        vals.get('price_unit', 0.0),
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        currency,
                        self.env['product.product'].browse(vals.get('product_id')),
                        partner,
                        taxes,
                        move.move_type,
                    ))
                elif any(vals.get(field) for field in BUSINESS_FIELDS):
                    vals.update(self._get_price_total_and_subtotal_model(
                        vals.get('price_unit', 0.0),
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        currency,
                        self.env['product.product'].browse(vals.get('product_id')),
                        partner,
                        taxes,
                        move.move_type,
                    ))
                    vals.update(self._get_fields_onchange_subtotal_model(
                        vals['price_subtotal'],
                        move.move_type,
                        currency,
                        move.company_id,
                        move.date,
                    ))

        lines = super(AccountMoveLine, self).create(vals_list)

        moves = lines.mapped('move_id')
        if self._context.get('check_move_validity', True):
            moves._check_balanced()
        moves.filtered(lambda m: m.state == 'posted')._check_fiscalyear_lock_date()
        lines.filtered(lambda l: l.parent_state == 'posted')._check_tax_lock_date()
        moves._synchronize_business_models({'line_ids'})

        return lines

class StockMove(models.Model):
    _inherit = 'stock.move'

    # wc = fields.Char('WC')
    deadline = fields.Char('Deadline')
    desc = fields.Char('Description')
    packing = fields.Many2one('product.packaging', 'Packaging')
    price = fields.Float('Product Price')
    # x_unit_price = fields.Char('X Price')

    def run_x_cron_job(self):
        lines = self.env['stock.move.line'].search([])
        for line in lines:
            if not line.price and line.x_unit_price:
                line.move_id.price = line.x_unit_price
                print(line.move_id.price)

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    price = fields.Char('Product Price')
    # x_unit_price = fields.Char('X Price')


class AccountMove(models.Model):
    _inherit = 'account.move'

    del_add = fields.Char('Delivery Address')
    lpo = fields.Char('LPO number')
    mark = fields.Char('Mark')
    do_ref = fields.Char('DO Reference')
    container = fields.Char('Container Number')
    seal = fields.Char('Seal Number')

    def action_post(self):
        gr = self.write_uid.groups_id.filtered(lambda a: a.name == 'Move Confirmation')
        if gr:
            if self.payment_id:
                self.payment_id.action_post()
            else:
                self._post(soft=False)
            return False
        else:
            raise ValidationError(_(
                "You are not allow to perform this operation. "
            ))

class ProductTemplate(models.Model):
    _inherit = "product.template"

    hs_code = fields.Char('HS Code')

    @api.model_create_multi
    def create(self, vals_list):
        ''' Store the initial standard price in order to be able to retrieve the cost of a product template for a given date'''
        is_right = True
        if self.env.context.get('uid'):
            users = self.env['res.users'].search([('id', '=', self.env.context.get('uid'))])
            gr = users.groups_id.filtered(lambda a: a.name == 'Product Creation')
            if gr:
                for vals in vals_list:
                    self._sanitize_vals(vals)
                templates = super(ProductTemplate, self).create(vals_list)
                if "create_product_product" not in self._context:
                    templates._create_variant_ids()

                # This is needed to set given values to first variant after creation
                for template, vals in zip(templates, vals_list):
                    related_vals = {}
                    if vals.get('barcode'):
                        related_vals['barcode'] = vals['barcode']
                    if vals.get('default_code'):
                        related_vals['default_code'] = vals['default_code']
                    if vals.get('standard_price'):
                        related_vals['standard_price'] = vals['standard_price']
                    if vals.get('volume'):
                        related_vals['volume'] = vals['volume']
                    if vals.get('weight'):
                        related_vals['weight'] = vals['weight']
                    # Please do forward port
                    if vals.get('packaging_ids'):
                        related_vals['packaging_ids'] = vals['packaging_ids']
                    if related_vals:
                        template.write(related_vals)
            else:
                is_right = False

        if not is_right:
            raise ValidationError(_(
                "You are not allow to perform this operation. "
            ))
        return templates


class StockLedger(models.Model):
    _name = 'stock.ledger'

    product_id = fields.Many2one('product.template', string="Product", required=True)
    from_date = fields.Datetime(string='From Date')
    to_date = fields.Datetime(string='To Date')
    stock_location = fields.Many2one('stock.location',string="Stock Location")
    def get_data(self):
        data = {
            'ids': self.ids,
            'model': 'stock.ledger',
            'form': self.read(),
            'product' : self.product_id,
            'from' : self.from_date,
            'to':self.to_date
        }
        vals = {}
        list = []
        layers = self.env['stock.valuation.layer'].search([('product_tmpl_id', '=', self.product_id.id),
                                                           ('create_date', '>=', self.from_date),('create_date', '<=', self.to_date)])
        opening = self.env['stock.quant'].search([('location_id','=',self.stock_location.id),('product_tmpl_id','=',self.product_id.id),('create_date', '>=', self.from_date),('create_date', '<=', self.to_date)])
        counter = 0
        for line in layers.filtered(lambda l: 'adjustment' not in l.stock_move_id.display_name):
            if line.stock_move_id.picking_code == 'outgoing' and line.stock_move_id.location_id == self.stock_location or line.stock_move_id.picking_code == 'incoming' and line.stock_move_id.location_dest_id == self.stock_location:
                vals = {'ref': line.stock_move_id.reference,
                        'date': line.create_date,
                        'party': self.get_partner_id(line),
                        'price': line.stock_move_id.price,
                        'in': line.quantity if line.quantity > 0 else False,
                        'out': line.quantity if line.quantity < 0 else False,
                        'balance': self.compute_blnce(counter,line,opening,vals)
                        }
                list.append(vals)
                counter +=1
        data['values'] = list
        return self.env.ref('eq_invoice_from_picking.stock_report').report_action(self, data)

    def compute_blnce(self,counter,line,opening,vals):
        if counter == 0:
            return opening.quantity
        else:
            if line.quantity < 0:
                b = vals.get('balance') + line.quantity
                return b
            if line.quantity > 0:
                b = vals.get('balance') + line.quantity
                return b333

    def get_partner_id(self, line):
        picking = self.env['stock.picking'].search([('name', '=', line.stock_move_id.reference)])
        return picking.partner_id.name

    def cancel(self):
        print()
