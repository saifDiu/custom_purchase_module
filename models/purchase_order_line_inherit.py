from odoo import api, fields, models
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    @api.depends('state')
    def _get_po_total_amount(self):
        for rec in self:
            if rec.move_type == 'in_invoice':
                po_amount_total = self.env['purchase.order'].search([('name', '=', rec.invoice_origin)]).amount_total
                po_amount_deduction = self.env['purchase.order'].search([('name', '=', rec.invoice_origin)]).total_deduction_amount
                rec.write({
                    'amount_total': po_amount_total,
                    'amount_residual':po_amount_total
                })
                rec.dummy_total_amount = po_amount_deduction
            else:
                rec.dummy_total_amount = 0.0

    dummy_total_amount = fields.Float(compute=_get_po_total_amount,string="Total Price Deduction")

    @api.model_create_multi
    def create(self, vals_list):
        res = super(AccountMoveInherit, self).create(vals_list)
        if res.move_type == 'in_invoice':
            po_amount_total = self.env['purchase.order'].search([('name','=',res.invoice_origin)]).amount_total
            res.write({
                'amount_total':po_amount_total
            })
        return res




class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'

    total_deduction_product = fields.Many2one('product.product',domain=[('total_deduction_ok','=',True)],string="Total Price Deduction")
    total_deduction_amount = fields.Float(string="Total Deduction Amount")

    @api.model
    def create(self, vals):
        res = super(PurchaseOrderInherit, self).create(vals)
        val = res.amount_total + res.total_deduction_amount
        res.write({
            'amount_total': val
        })
        return res


    @api.onchange('total_deduction_product')
    def onchange_total_deduction(self):
        deduction_amount = (self.amount_total * self.total_deduction_product.deduction_percentage_field) / 100
        val = self.amount_total - deduction_amount
        self.total_deduction_amount = deduction_amount
        self.write({
            'amount_total':val,
            'tax_totals_json': val,
            'total_deduction_amount':-deduction_amount
        })

class PurchaseOrderLineInherit(models.Model):
    _inherit = 'purchase.order.line'

    @api.onchange('product_id')
    def onchange_product_id(self):
        if not self.product_id:
            return

        # Reset date, price and quantity since _onchange_quantity will provide default values
        self.price_unit = self.product_qty = 0.0

        self._product_id_change()

        self._suggest_quantity()
        self._onchange_quantity()

    @api.onchange('product_qty', 'product_uom')
    def _onchange_quantity(self):
        if not self.product_id:
            return
        params = {'order_id': self.order_id}
        seller = self.product_id._select_seller(
            partner_id=self.partner_id,
            quantity=self.product_qty,
            date=self.order_id.date_order and self.order_id.date_order.date(),
            uom_id=self.product_uom,
            params=params)

        if seller or not self.date_planned:
            self.date_planned = self._get_date_planned(seller).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        # If not seller, use the standard price. It needs a proper currency conversion.
        if not seller:
            po_line_uom = self.product_uom or self.product_id.uom_po_id
            price_unit = self.env['account.tax']._fix_tax_included_price_company(
                self.product_id.uom_id._compute_price(self.product_id.standard_price, po_line_uom),
                self.product_id.supplier_taxes_id,
                self.taxes_id,
                self.company_id,
            )
            if price_unit and self.order_id.currency_id and self.order_id.company_id.currency_id != self.order_id.currency_id:
                price_unit = self.order_id.company_id.currency_id._convert(
                    price_unit,
                    self.order_id.currency_id,
                    self.order_id.company_id,
                    self.date_order or fields.Date.today(),
                )
            if self.product_id.subtotal_deduction_ok:
                subtotal_amount = 0.0
                for rec in self.order_id.order_line:
                    if not rec.product_id.subtotal_deduction_ok:
                        subtotal_amount += rec.price_subtotal
                deduction_amount = (subtotal_amount * self.product_id.deduction_percentage_field) / 100
                self.price_unit = -deduction_amount
            else:
                self.price_unit = price_unit
            return

        price_unit = self.env['account.tax']._fix_tax_included_price_company(seller.price,
                                                                             self.product_id.supplier_taxes_id,
                                                                             self.taxes_id,
                                                                             self.company_id) if seller else 0.0
        if price_unit and seller and self.order_id.currency_id and seller.currency_id != self.order_id.currency_id:
            price_unit = seller.currency_id._convert(
                price_unit, self.order_id.currency_id, self.order_id.company_id, self.date_order or fields.Date.today())

        if seller and self.product_uom and seller.product_uom != self.product_uom:
            price_unit = seller.product_uom._compute_price(price_unit, self.product_uom)

        if self.product_id.subtotal_deduction_ok:
            subtotal_amount = 0.0
            for rec in self.order_id.order_line:
                if not rec.product_id.subtotal_deduction_ok:
                    subtotal_amount += rec.price_subtotal
            deduction_amount = (subtotal_amount * self.product_id.deduction_percentage_field) / 100
            self.price_unit = -deduction_amount
        else:
            self.price_unit = price_unit