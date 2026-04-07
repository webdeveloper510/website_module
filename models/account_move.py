from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    def action_post(self):
        """Override to mark slots as booked when invoice is posted"""
        res = super(AccountMove, self).action_post()
        
        # Process only customer invoices
        for invoice in self.filtered(lambda inv: inv.move_type == 'out_invoice'):
            # Find related sale order
            if invoice.invoice_origin:
                sale_orders = self.env['sale.order'].search([
                    ('name', '=', invoice.invoice_origin)
                ])
                
                for order in sale_orders:
                    # Find and mark all slots related to this sale order
                    slots = self.env['product.slot'].search([
                        ('sale_id', '=', order.id)
                    ])
                    
                    if slots:
                        slots.write({
                            'is_booked': True,
                            'is_paid': True
                        })
        
        return res
    
    def button_draft(self):
        """Override to unmark slots when invoice is reset to draft"""
        res = super(AccountMove, self).button_draft()
        
        # Unmark slots when invoice is cancelled/reset
        for invoice in self.filtered(lambda inv: inv.move_type == 'out_invoice'):
            if invoice.invoice_origin:
                sale_orders = self.env['sale.order'].search([
                    ('name', '=', invoice.invoice_origin)
                ])
                
                for order in sale_orders:
                    slots = self.env['product.slot'].search([
                        ('sale_id', '=', order.id)
                    ])
                    
                    if slots:
                        slots.write({
                            'is_booked': False,
                            'is_paid': False
                        })
        
        return res
    
    def button_cancel(self):
        """Override to unmark slots when invoice is cancelled"""
        # Unmark slots before cancelling
        for invoice in self.filtered(lambda inv: inv.move_type == 'out_invoice'):
            if invoice.invoice_origin:
                sale_orders = self.env['sale.order'].search([
                    ('name', '=', invoice.invoice_origin)
                ])
                
                for order in sale_orders:
                    slots = self.env['product.slot'].search([
                        ('sale_id', '=', order.id)
                    ])
                    
                    if slots:
                        slots.write({
                            'is_booked': False,
                            'is_paid': False
                        })
        
        res = super(AccountMove, self).button_cancel()
        return res