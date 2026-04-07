from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SubscriptionDiscountConfig(models.Model):
    _name = 'subscription.discount.config'
    _description = 'Subscription Discount Configuration'
    _rec_name = 'name'
    
    name = fields.Char(string='Configuration Name', required=True, default='Subscription Discounts')
    
    # ✅ SEPARATE DISCOUNT FIELDS FOR EACH MEMBERSHIP TYPE
    
    # Membership A Discounts
    sub_a_lane_rental = fields.Integer(string='Membership A - Lane Rental (%)', default=0)
    sub_a_merchandise = fields.Integer(string='Membership A - Merchandise (%)', default=0)
    
    # Membership B Discounts
    sub_b_lane_rental = fields.Integer(string='Membership B - Lane Rental (%)', default=0)
    sub_b_merchandise = fields.Integer(string='Membership B - Merchandise (%)', default=0)
    
    # Membership C Discounts
    sub_c_lane_rental = fields.Integer(string='Membership C - Lane Rental (%)', default=0)
    sub_c_merchandise = fields.Integer(string='Membership C - Merchandise (%)', default=0)
    
    # Category-specific discounts (per subscription type)
    category_discount_ids = fields.One2many(
        'subscription.category.discount',
        'config_id',
        string='Category-Specific Discounts'
    )
    
    # Filtered One2many fields for each membership type
    category_discount_a_ids = fields.One2many(
        'subscription.category.discount',
        'config_id',
        string='Membership A Category Discounts',
        domain=[('subscription_type', '=', 'subscription_a')]
    )
    
    category_discount_b_ids = fields.One2many(
        'subscription.category.discount',
        'config_id',
        string='Membership B Category Discounts',
        domain=[('subscription_type', '=', 'subscription_b')]
    )
    
    category_discount_c_ids = fields.One2many(
        'subscription.category.discount',
        'config_id',
        string='Membership C Category Discounts',
        domain=[('subscription_type', '=', 'subscription_c')]
    )
    
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('unique_config', 
         'UNIQUE(name)', 
         'Only one discount configuration can be active!')
    ]
    
    @api.model
    def get_active_config(self):
        """Get the active discount configuration"""
        return self.sudo().search([('active', '=', True)], limit=1)
    
    @api.model
    def is_discount_enabled(self):
        """Check if discount system is enabled globally"""
        config = self.sudo().get_active_config()
        return bool(config)
    
    def get_discounts_for_subscription(self, subscription_type):
        """Get discount values for a specific subscription type"""
        self.ensure_one()
        
        # Map subscription type to discount fields
        discount_map = {
            'subscription_a': {
                'lane_rental_discount': self.sub_a_lane_rental,
                'merchandise_discount': self.sub_a_merchandise,
            },
            'subscription_b': {
                'lane_rental_discount': self.sub_b_lane_rental,
                'merchandise_discount': self.sub_b_merchandise,
            },
            'subscription_c': {
                'lane_rental_discount': self.sub_c_lane_rental,
                'merchandise_discount': self.sub_c_merchandise,
            },
        }
        
        # Get base discounts for this subscription type
        base_discounts = discount_map.get(subscription_type, {
            'lane_rental_discount': 0,
            'merchandise_discount': 0,
        })
        
        # Build category discounts list for this subscription type
        category_discounts = []
        for line in self.category_discount_ids.filtered(
            lambda x: x.subscription_type == subscription_type
        ):
            category_discounts.append({
                'category_id': line.category_id.id,
                'category_name': line.category_id.name,
                'discount_percent': line.discount_percent,
            })
        
        return {
            'lane_rental_discount': base_discounts['lane_rental_discount'],
            'merchandise_discount': base_discounts['merchandise_discount'],
            'category_discounts': category_discounts,
        }
    
    def apply_to_all_subscriptions(self):
        """Apply current discount config to all active subscriptions"""
        self.ensure_one()
        
        active_subscriptions = self.env['user.subscription'].search([
            ('status', '=', 'active')
        ])
        
        for subscription in active_subscriptions:
            subscription._create_subscription_pricelist()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Updated {len(active_subscriptions)} active subscriptions',
                'type': 'success',
                'sticky': False,
            }
        }
    
    def write(self, vals):
        """When deactivating, remove pricelists from affected users"""
        result = super(SubscriptionDiscountConfig, self).write(vals)
        
        # If deactivating the config
        if 'active' in vals and not vals['active']:
            subscriptions = self.env['user.subscription'].search([
                ('status', '=', 'active')
            ])
            
            default_pricelist = self.env['product.pricelist'].sudo().search([
                ('name', '=', 'Public Pricelist')
            ], limit=1)
            
            if not default_pricelist:
                default_pricelist = self.env['product.pricelist'].sudo().search([], limit=1)
            
            for subscription in subscriptions:
                subscription.partner_id.property_product_pricelist = default_pricelist.id
                if subscription.pricelist_id:
                    subscription.pricelist_id.active = False
        
        # If activating the config
        elif 'active' in vals and vals['active']:
            subscriptions = self.env['user.subscription'].search([
                ('status', '=', 'active')
            ])
            
            for subscription in subscriptions:
                subscription._create_subscription_pricelist()
        
        return result


class SubscriptionCategoryDiscount(models.Model):
    _name = 'subscription.category.discount'
    _description = 'Category-Specific Subscription Discount'
    
    config_id = fields.Many2one('subscription.discount.config', string='Configuration', required=True, ondelete='cascade')
    
    # ✅ NEW: Link discount to specific subscription type
    subscription_type = fields.Selection([
        ('subscription_a', 'Membership A'),
        ('subscription_b', 'Membership B'),
        ('subscription_c', 'Membership C'),
    ], string='Membership Type', required=True)
    
    category_id = fields.Many2one('product.category', string='Product Category', required=True)
    discount_percent = fields.Float(string='Discount (%)', required=True, default=10.0)
    
    _sql_constraints = [
        ('unique_category_subscription', 
         'UNIQUE(config_id, subscription_type, category_id)', 
         'Each category can only have one discount per subscription type!')
    ]