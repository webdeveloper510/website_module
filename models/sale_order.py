# models/sale_order.py
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    @api.model
    def create(self, vals):
        """Apply subscription discount when line is created"""
        line = super(SaleOrderLine, self).create(vals)
        line._apply_subscription_discount()
        return line
    
    def write(self, vals):
        """Apply subscription discount when line is updated"""
        res = super(SaleOrderLine, self).write(vals)
        if 'product_id' in vals or 'product_uom_qty' in vals:
            self._apply_subscription_discount()
        return res
    
    def _apply_subscription_discount(self):
        """Apply discount based on subscription status"""
        for line in self:
            # Skip if no order or partner
            if not line.order_id or not line.order_id.partner_id:
                continue
            
            # Check if partner has active subscription
            if line.order_id.partner_id.has_active_subscription:
                subscription = line.order_id.partner_id.active_subscription_id
                
                if not subscription:
                    continue
                
                discount = 0.0
                product_name = line.product_id.name.lower()
                category_name = line.product_id.categ_id.name if line.product_id.categ_id else ''
                
                # Apply discount based on product type
                if 'lane' in product_name or 'lane' in category_name.lower():
                    discount = subscription.lane_rental_discount
                elif 'merchandise' in category_name.lower() or 'merch' in product_name:
                    discount = subscription.merchandise_discount
                
                # Apply the discount
                if discount > 0:
                    line.discount = discount


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    is_rental_order = fields.Boolean(string='Is Rental Order', default=False)
    rental_start_date = fields.Datetime(string='Rental Start Date')
    rental_return_date = fields.Datetime(string='Rental Return Date')
    selected_slots = fields.Text(string='Selected Slots (JSON)')
    selected_addons = fields.Text(string='Selected Add-ons (JSON)')
    extra_addons_ids = fields.One2many('extra.addons', 'sale_id', string="Extra Addons")
    def get_unique_addons(self):
        """Return unique addon product names for the sale order to avoid duplicates in dashboard."""
        self.ensure_one()
        return list(set(self.extra_addons_ids.mapped('product_addons_id.name')))
    def apply_subscription_discount_line(self):
        """
        Apply subscription-based discounts to sale order lines
        Uses subscription-type-specific discount fields
        """
        self.ensure_one()
        today = fields.Date.today()
        
        _logger.info("=== Starting apply_subscription_discount_line ===")
        
        # FIX: Use status='active' + end_date guard, matching _compute_active_subscription logic.
        # The previous search omitted status='active' and required start_date to be set,
        # which caused discounts to silently not apply for many valid subscribers.
        active_subscription = self.env['user.subscription'].sudo().search([
            ('partner_id', '=', self.partner_id.id),
            ('status', '=', 'active'),
            ('end_date', '>=', today),
        ], limit=1)

        if not active_subscription:
            _logger.info("No active subscription found")
            return
        
        _logger.info(f"Active subscription found: {active_subscription.subscription_type}")
        
        # Check if discount is enabled
        discount_config = self.env['subscription.discount.config'].sudo().get_active_config()
        if not discount_config:
            _logger.info("No active discount config found")
            return
        
        # ✅ Get subscription-specific discounts using the helper method
        subscription_type = active_subscription.subscription_type
        discounts = discount_config.get_discounts_for_subscription(subscription_type)
        
        lane_rental_discount = discounts.get('lane_rental_discount', 0)
        merchandise_discount = discounts.get('merchandise_discount', 0)
        category_discounts = discounts.get('category_discounts', [])
        
        _logger.info(f"Discounts for {subscription_type}: Lane={lane_rental_discount}%, Merchandise={merchandise_discount}%")
        _logger.info(f"Category-specific discounts: {len(category_discounts)} configured")
        
        # Create mapping of category_id to discount for quick lookup
        category_discount_map = {
            cd['category_id']: cd['discount_percent'] 
            for cd in category_discounts
        }
        
        # Apply discount to each order line
        for line in self.order_line:
            product = line.product_id
            discount_to_apply = 0.0
            discount_source = "None"
            
            _logger.info(f"Processing product: {product.name}, Category: {product.categ_id.name if product.categ_id else 'None'}")
            
            # Priority 1: Check for category-specific discount
            if product.categ_id and product.categ_id.id in category_discount_map:
                discount_to_apply = category_discount_map[product.categ_id.id]
                discount_source = f"Category '{product.categ_id.name}'"
                _logger.info(f"  → Category-specific discount: {discount_to_apply}%")
            
            # Priority 2: Check product type or category keywords for base discounts
            elif product.categ_id:
                category_name = product.categ_id.name.lower()
                product_name = product.name.lower()
                
                _logger.info(f"  → Checking general category: {category_name}")
                
                # Check if it's a lane rental product
                if any(keyword in category_name for keyword in ['lane', 'rental', 'rentals', 'cricket', 'sports']):
                    discount_to_apply = lane_rental_discount
                    discount_source = "Lane Rental (Base)"
                    _logger.info(f"  → Lane rental discount applied: {discount_to_apply}%")
                
                # Check if it's a merchandise product
                elif any(keyword in category_name for keyword in ['merchandise', 'product', 'gear', 'equipment']):
                    discount_to_apply = merchandise_discount
                    discount_source = "Merchandise (Base)"
                    _logger.info(f"  → Merchandise discount applied: {discount_to_apply}%")
                
                # Check product_type attribute if it exists
                elif hasattr(product, 'product_type'):
                    if product.product_type == 'lane_rental':
                        discount_to_apply = lane_rental_discount
                        discount_source = "Lane Rental Type"
                        _logger.info(f"  → Lane rental (by type) discount: {discount_to_apply}%")
                    elif product.product_type == 'merchandise':
                        discount_to_apply = merchandise_discount
                        discount_source = "Merchandise Type"
                        _logger.info(f"  → Merchandise (by type) discount: {discount_to_apply}%")
                else:
                    _logger.info(f"  → No matching category found for: {category_name}")
            
            # Apply discount if any
            if discount_to_apply > 0 and line.price_unit > 0:
                peak_amount = 0.0
                non_peak_amount = line.price_unit
                
                # Exclude peak slots from subscription discounts
                if product.product_tmpl_id.product_type == 'lane_rental' or product.product_tmpl_id.is_box_cricket:
                    product_slots = self.env['product.slot'].sudo().search([
                        ('sale_id', '=', self.id),
                        ('product_id', '=', product.id)
                    ])
                    
                    peak_price = product.product_tmpl_id.peak_price or 0.0
                    peak_times = product.product_tmpl_id.peak_time_ids
                    
                    if peak_price > 0 and peak_times:
                        peak_count = 0
                        for slot in product_slots:
                            slot_time = slot.time_slot
                            slot_date = slot.date
                            if slot_date and slot_time:
                                day_of_week = slot_date.strftime('%A').lower()
                                time_parts = slot_time.split(" ")
                                if len(time_parts) == 2:
                                    time_str, period = time_parts
                                    try:
                                        hours, mins = map(int, time_str.split(":"))
                                        if period == "PM" and hours != 12: hours += 12
                                        if period == "AM" and hours == 12: hours = 0
                                        time_val = hours + (mins / 60.0)
                                        
                                        is_peak = False
                                        for pt in peak_times:
                                            if pt.days == day_of_week:
                                                p_start_parts = pt.start_time.split(" ")
                                                p_start_h, p_start_m = map(int, p_start_parts[0].split(":"))
                                                if p_start_parts[1] == "PM" and p_start_h != 12: p_start_h += 12
                                                if p_start_parts[1] == "AM" and p_start_h == 12: p_start_h = 0
                                                p_start_val = p_start_h + (p_start_m / 60.0)
                                                
                                                p_end_parts = pt.end_time.split(" ")
                                                p_end_h, p_end_m = map(int, p_end_parts[0].split(":"))
                                                if p_end_parts[1] == "PM" and p_end_h != 12: p_end_h += 12
                                                if p_end_parts[1] == "AM" and p_end_h == 12: p_end_h = 0
                                                p_end_val = p_end_h + (p_end_m / 60.0)
                                                
                                                if time_val >= p_start_val and time_val < p_end_val:
                                                    is_peak = True
                                                    break
                                        if is_peak:
                                            peak_count += 1
                                    except ValueError:
                                        pass
                                        
                        peak_amount = peak_count * peak_price
                        non_peak_amount = max(0.0, line.price_unit - peak_amount)

                # Calculate the discounted price
                discount_multiplier = (100 - discount_to_apply) / 100.0
                original_price = line.price_unit
                discounted_non_peak = non_peak_amount * discount_multiplier
                discounted_price = peak_amount + discounted_non_peak
                
                # Update the line with new price
                line.write({
                    'price_unit': discounted_price,
                    'discount': 0,  # Reset discount field if using direct price reduction
                })
                
                _logger.info(f"  ✓ Applied {discount_to_apply}% discount ({discount_source})")
                _logger.info(f"    Original: ${original_price:.2f} → Discounted: ${discounted_price:.2f} (Peak Amount: ${peak_amount:.2f})")
            else:
                _logger.info(f"  × No discount applied (discount={discount_to_apply}%, price=${line.price_unit:.2f})")
        
        # Recalculate order totals
        self._compute_tax_totals()
        
        _logger.info("=== Finished apply_subscription_discount_line ===")
        _logger.info(f"Order total after discount: ${self.amount_total:.2f}")
