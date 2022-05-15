from odoo import api, fields, models


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    gold_purity = fields.Float(string="Gold Purity")

    subtotal_deduction_ok = fields.Boolean(string="Price Subtotal Deduction")
    total_deduction_ok = fields.Boolean(string="Price Total Deduction")

    deduction_percentage_field = fields.Float(string="Deduction Percentage")
