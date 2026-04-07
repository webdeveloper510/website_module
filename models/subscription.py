from odoo import models, fields, api
from datetime import timedelta


class SubscriptionGroup(models.Model):
    _name = 'subscription.group'
    _description = 'Subscription Group'
    _rec_name = 'name'

    name = fields.Char(string='Group Name', required=True)
    description = fields.Text(string='Description')

    # Which membership types belong to this group (configured by admin, not per-member)
    type_config_ids = fields.One2many(
        'subscription.type.config',
        'group_id',
        string='Membership Types in this Group'
    )

    _sql_constraints = [
        ('unique_group_name', 'UNIQUE(name)', 'Group name must be unique!')
    ]

    def unlink(self):
        """Prevent deletion if membership types are still assigned to this group"""
        if self.type_config_ids:
            raise models.ValidationError(
                'Cannot delete a subscription group that still has membership types assigned to it. '
                'Please reassign or clear the membership types first.'
            )
        return super().unlink()


class SubscriptionTypeConfig(models.Model):
    """Admin-level config: maps each membership type (A, B, C) to a group.
    This is set once by an administrator, not per individual subscriber.
    """
    _name = 'subscription.type.config'
    _description = 'Membership Type Configuration'
    _rec_name = 'subscription_type'

    subscription_type = fields.Selection([
        ('subscription_a', 'Membership A'),
        ('subscription_b', 'Membership B'),
        ('subscription_c', 'Membership C'),
        ('monthly', '[Legacy] Monthly Subscription'),
    ], string='Membership Type', required=True)

    group_id = fields.Many2one(
        'subscription.group',
        string='Group',
        ondelete='restrict',
        help='Memberships in the same group are mutually exclusive.'
    )

    _sql_constraints = [
        ('unique_subscription_type', 'UNIQUE(subscription_type)',
         'Each membership type can only have one configuration entry.')
    ]

    @api.model
    def get_group_for_type(self, subscription_type):
        """Return the group_id (int) for a given subscription_type, or None."""
        config = self.search([('subscription_type', '=', subscription_type)], limit=1)
        return config.group_id.id if config and config.group_id else None

    @api.model
    def get_type_group_map(self):
        """Return a dict {subscription_type: group_id} for all configured types."""
        configs = self.search([])
        return {
            c.subscription_type: c.group_id.id
            for c in configs
            if c.group_id
        }


class UserSubscription(models.Model):
    _name = 'user.subscription'
    _description = 'User Subscription Management'
    
    user_id = fields.Many2one('res.users', string='User', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    
    subscription_type = fields.Selection([
        ('subscription_a', 'Membership A'),
        ('subscription_b', 'Membership B'),
        ('subscription_c', 'Membership C'),
        ('monthly', '[Legacy] Monthly Subscription'),
    ], string='Subscription Type', default='subscription_a', required=True)

    
    price = fields.Float(string='Monthly Price', default=20.00, digits=(16, 2))
    
    status = fields.Selection([
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('pending', 'Pending Payment')
    ], string='Status', default='pending', required=True)
    
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    next_billing_date = fields.Date(string='Next Billing Date')
    cancelled_date = fields.Date(string='Cancellation Date')
    
    # Stripe fields
    stripe_subscription_id = fields.Char(string='Stripe Subscription ID')
    stripe_customer_id = fields.Char(string='Stripe Customer ID')
    stripe_price_id = fields.Char(string='Stripe Price ID', help='The Stripe Price ID used for this subscription')
    
    gym_access = fields.Boolean(string='Gym Access', default=True)
    lane_rental_discount = fields.Integer(string='Lane Rental Discount (%)', default=0)
    merchandise_discount = fields.Integer(string='Merchandise Discount (%)', default=0)
    
    is_active = fields.Boolean(string='Is Active', compute='_compute_is_active', store=True)
    days_remaining = fields.Integer(string='Days Remaining', compute='_compute_days_remaining')
    
    pricelist_id = fields.Many2one('product.pricelist', string='Subscription Pricelist')

    discount_config_id = fields.Many2one(
        'subscription.discount.config',
        compute='_compute_discount_config',
        store=False
    )

    benefit_lines = fields.Json(
        string='Subscription Benefits',
        compute='_compute_benefit_lines'
    )
    
    subscription_type_display = fields.Char(
        string='Membership Type',
        compute='_compute_subscription_type_display',
        store=True
    )

    @api.depends('subscription_type')
    def _compute_subscription_type_display(self):
        """Compute display name for subscription type"""
        type_names = {
            'subscription_a': 'Membership A',
            'subscription_b': 'Membership B',
            'subscription_c': 'Membership C',
            'monthly': 'Monthly Subscription (Legacy)',
        }
        for record in self:
            record.subscription_type_display = type_names.get(
                record.subscription_type, 
                'Unknown'
            )

    def _compute_discount_config(self):
        """Get the active discount config"""
        for sub in self:
            config = self.env['subscription.discount.config'].sudo().get_active_config()
            sub.discount_config_id = config

    def _compute_benefit_lines(self):
        """Compute benefit lines with discounts based on subscription type"""
        for sub in self:
            benefits = []
            used_categories = set()

            config = sub.discount_config_id

            if not config:
                sub.benefit_lines = benefits
                continue

            # Handle legacy subscriptions
            sub_type = sub.subscription_type
            if sub_type == 'monthly':
                sub_type = 'subscription_a'

            # 1️⃣ Category discounts (highest priority)
            for line in config.category_discount_ids.filtered(
                lambda x: x.subscription_type == sub_type
            ):
                category_name = line.category_id.name
                
                benefits.append({
                    'label': category_name,
                    'discount': line.discount_percent,
                })
                normalized = category_name.lower().rstrip('s')
                used_categories.add(normalized)

            # 2️⃣ Global discounts ONLY if no category discount exists
            if sub.lane_rental_discount and 'lane rental' not in used_categories:
                benefits.append({
                    'label': 'Lane Rentals',
                    'discount': sub.lane_rental_discount,
                })

            if sub.merchandise_discount and 'merchandise' not in used_categories:
                benefits.append({
                    'label': 'Merchandise',
                    'discount': sub.merchandise_discount,
                })

            sub.benefit_lines = benefits

    @api.model
    def create(self, vals):
        """Create pricelist when subscription is created"""
        record = super(UserSubscription, self).create(vals)
        
        # Handle legacy 'monthly' type
        sub_type = record.subscription_type
        if sub_type == 'monthly':
            sub_type = 'subscription_a'
        
        # Get active config
        config = self.env['subscription.discount.config'].sudo().get_active_config()
        
        if config:
            # Apply discounts from config based on subscription type
            discounts = config.get_discounts_for_subscription(sub_type)
            record.write({
                'lane_rental_discount': discounts['lane_rental_discount'],
                'merchandise_discount': discounts['merchandise_discount'],
            })
            record._create_subscription_pricelist()
        else:
            # Set to default pricelist
            default_pricelist = self.env['product.pricelist'].sudo().search([
                ('name', '=', 'Public Pricelist')
            ], limit=1)
            if default_pricelist:
                record.partner_id.property_product_pricelist = default_pricelist.id
        
        return record
    
    def _create_subscription_pricelist(self):
        """Always use default pricelist - discount applied as line item"""
        self.ensure_one()
        
        # Get default pricelist
        default_pricelist = self.env['product.pricelist'].sudo().search([
            ('name', '=', 'Public Pricelist')
        ], limit=1)
        
        if not default_pricelist:
            default_pricelist = self.env['product.pricelist'].sudo().search([
                ('active', '=', True),
                ('company_id', '=', self.env.company.id)
            ], order='id', limit=1)
        
        # Always set to default pricelist
        if default_pricelist:
            self.partner_id.property_product_pricelist = default_pricelist.id
        
        # Remove any existing subscription pricelist
        if self.pricelist_id:
            old_pricelist = self.pricelist_id
            self.pricelist_id = False
            try:
                old_pricelist.unlink()
            except:
                old_pricelist.active = False

    def action_update_pricelist(self):
        """Update pricelist with new discount values"""
        self.ensure_one()
        
        # Handle legacy 'monthly' type
        sub_type = self.subscription_type
        if sub_type == 'monthly':
            sub_type = 'subscription_a'
        
        # Get active discount configuration
        config = self.env['subscription.discount.config'].sudo().get_active_config()
        
        if not config:
            if self.pricelist_id:
                self.pricelist_id.unlink()
                self.pricelist_id = False
            
            default_pricelist = self.env['product.pricelist'].sudo().search([
                ('name', '=', 'Public Pricelist')
            ], limit=1)
            if default_pricelist:
                self.partner_id.property_product_pricelist = default_pricelist.id
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Discount Config',
                    'message': 'No active discount configuration found. Using default pricing.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Apply discounts from config based on subscription type
        discounts = config.get_discounts_for_subscription(sub_type)
        self.write({
            'lane_rental_discount': discounts['lane_rental_discount'],
            'merchandise_discount': discounts['merchandise_discount'],
        })
        
        # Recreate pricelist with new values
        self._create_subscription_pricelist()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Pricelist updated successfully. Lane: {discounts["lane_rental_discount"]}%, Merch: {discounts["merchandise_discount"]}%',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.depends('status', 'end_date')
    def _compute_is_active(self):
        today = fields.Date.today()
        for record in self:
            record.is_active = (
                record.status == 'active' and 
                record.end_date and 
                record.end_date >= today
            )
    
    @api.depends('end_date')
    def _compute_days_remaining(self):
        today = fields.Date.today()
        for record in self:
            if record.end_date and record.end_date >= today:
                record.days_remaining = (record.end_date - today).days
            else:
                record.days_remaining = 0
    
    def action_cancel_subscription(self):
        """Cancel subscription and remove pricelist"""
        self.ensure_one()
        
        default_pricelist = self.env['product.pricelist'].sudo().search([
            ('name', '=', 'Public Pricelist')
        ], limit=1)
        
        if not default_pricelist:
            default_pricelist = self.env['product.pricelist'].sudo().search([], limit=1)
            
        self.partner_id.property_product_pricelist = default_pricelist.id
        
        if self.pricelist_id:
            self.pricelist_id.active = False
        
        self.write({
            'status': 'cancelled',
            'cancelled_date': fields.Date.today()
        })
        return True
    
    def action_renew_subscription(self):
        """Renew subscription for another month"""
        self.ensure_one()
        if self.end_date:
            new_end_date = self.end_date + timedelta(days=30)
        else:
            new_end_date = fields.Date.today() + timedelta(days=30)
        
        self.write({
            'end_date': new_end_date,
            'next_billing_date': new_end_date,
            'status': 'active'
        })
    
    @api.model
    def migrate_legacy_subscriptions(self):
        """Migrate old 'monthly' subscriptions to proper subscription types"""
        legacy_subs = self.search([('subscription_type', '=', 'monthly')])
        
        for sub in legacy_subs:
            sub.write({'subscription_type': 'subscription_a'})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migration Complete',
                'message': f'Migrated {len(legacy_subs)} legacy subscriptions to Membership A',
                'type': 'success',
                'sticky': False,
            }
        }


class ResPartner(models.Model):
    _inherit = 'res.partner'

    stripe_customer_id = fields.Char(
        string='Stripe Customer ID',
        copy=False,
        index=True
    )

    subscription_ids = fields.One2many(
        'user.subscription', 'partner_id', string='Subscriptions'
    )

    active_subscription_ids = fields.Many2many(
        'user.subscription',
        compute='_compute_active_subscription',
        string='Active Subscriptions'
    )

    # Kept for backward compat – returns first active sub (or empty)
    active_subscription_id = fields.Many2one(
        'user.subscription',
        compute='_compute_active_subscription',
        string='Primary Active Subscription'
    )

    has_active_subscription = fields.Boolean(
        compute='_compute_active_subscription',
        string='Has Active Subscription'
    )

    @api.depends('subscription_ids.status', 'subscription_ids.end_date')
    def _compute_active_subscription(self):
        today = fields.Date.today()
        for partner in self:
            active_subs = partner.subscription_ids.filtered(
                lambda s: s.status == 'active' and s.end_date and s.end_date >= today
            )
            partner.active_subscription_ids = active_subs
            partner.active_subscription_id = active_subs[:1]
            partner.has_active_subscription = bool(active_subs)

    def get_active_subscription_for_group(self, group_id):
        """Return the active subscription for a specific group (or False).
        Looks up group membership via SubscriptionTypeConfig (type-level config).
        """
        self.ensure_one()
        today = fields.Date.today()
        # Get all subscription types that belong to this group
        type_configs = self.env['subscription.type.config'].search([
            ('group_id', '=', group_id)
        ])
        types_in_group = type_configs.mapped('subscription_type')
        if not types_in_group:
            return self.env['user.subscription']
        return self.subscription_ids.filtered(
            lambda s: s.status == 'active'
            and s.end_date
            and s.end_date >= today
            and s.subscription_type in types_in_group
        )[:1]