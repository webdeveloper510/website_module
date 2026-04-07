from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta

TIME_SLOTS = [

    ('12:00 AM', '12:00 AM'), ('12:30 AM', '12:30 AM'),
    ('01:00 AM', '01:00 AM'), ('01:30 AM', '01:30 AM'),
    ('02:00 AM', '02:00 AM'), ('02:30 AM', '02:30 AM'),
    ('03:00 AM', '03:00 AM'), ('03:30 AM', '03:30 AM'),
    ('04:00 AM', '04:00 AM'), ('04:30 AM', '04:30 AM'),
    ('05:00 AM', '05:00 AM'), ('05:30 AM', '05:30 AM'),
    ('06:00 AM', '06:00 AM'), ('06:30 AM', '06:30 AM'),
    ('07:00 AM', '07:00 AM'), ('07:30 AM', '07:30 AM'),
    ('08:00 AM', '08:00 AM'), ('08:30 AM', '08:30 AM'),
    ('09:00 AM', '09:00 AM'), ('09:30 AM', '09:30 AM'),
    ('10:00 AM', '10:00 AM'), ('10:30 AM', '10:30 AM'),
    ('11:00 AM', '11:00 AM'), ('11:30 AM', '11:30 AM'),
    ('12:00 PM', '12:00 PM'), ('12:30 PM', '12:30 PM'),
    ('01:00 PM', '01:00 PM'), ('01:30 PM', '01:30 PM'),
    ('02:00 PM', '02:00 PM'), ('02:30 PM', '02:30 PM'),
    ('03:00 PM', '03:00 PM'), ('03:30 PM', '03:30 PM'),
    ('04:00 PM', '04:00 PM'), ('04:30 PM', '04:30 PM'),
    ('05:00 PM', '05:00 PM'), ('05:30 PM', '05:30 PM'),
    ('06:00 PM', '06:00 PM'), ('06:30 PM', '06:30 PM'),
    ('07:00 PM', '07:00 PM'), ('07:30 PM', '07:30 PM'),
    ('08:00 PM', '08:00 PM'), ('08:30 PM', '08:30 PM'),
    ('09:00 PM', '09:00 PM'), ('09:30 PM', '09:30 PM'),
    ('10:00 PM', '10:00 PM'), ('10:30 PM', '10:30 PM'),
    ('11:00 PM', '11:00 PM'), ('11:30 PM', '11:30 PM')
]


class AddOns(models.Model):
    _name = 'extra.addons'
    _description = 'Extra Addons'

    date = fields.Date("Date")
    time = fields.Selection(TIME_SLOTS,"Time")
    product_addons_id = fields.Many2one('product.template')
    sale_id = fields.Many2one('sale.order',"Sale Order")
    is_book = fields.Boolean("Is Booked")
    product_addons_attribute_id = fields.Many2one('product.template.attribute.value')
    is_paid = fields.Boolean("Is Paid")

class TimeSlots(models.Model):
    _name = 'time.slot'
    _description = 'Time Slot'

    days = fields.Selection([
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday')
    ], string="Day",)

    morning_start_time = fields.Selection(
        TIME_SLOTS, string="Morning Start Time", required=True,
    )
    morning_end_time = fields.Selection(
        TIME_SLOTS,
    )
    morning_price = fields.Float(string="Morning Shift Price")

    evening_start_time = fields.Selection(
        TIME_SLOTS, string="Evening Start Time", required=True,
    )
    evening_end_time = fields.Selection(
        TIME_SLOTS, string="Evening End Time", required=True,
    )
    morning_price = fields.Float(string="Morning Price")
    evening_price = fields.Float(string="Evening Price")

    product_id = fields.Many2one('product.template',"Product Id")

    @api.constrains('days', 'product_id')
    def _check_duplicate_day(self):
        for record in self:
            existing_slot = self.search([
                ('days', '=', record.days),
                ('product_id', '=', record.product_id.id),
                ('id', '!=', record.id)
            ])
            if existing_slot:
                raise ValidationError(
                    f"A slot for {record.days.capitalize()} already exists for this product!"
                )

class ProductPeakTime(models.Model):
    _name = 'product.peak.time'
    _description = 'Product Peak Time'

    product_id = fields.Many2one('product.template', string="Product")
    days = fields.Selection([
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday')
    ], string="Day", required=True)
    
    start_time = fields.Selection(TIME_SLOTS, string="Start Time", required=True)
    end_time = fields.Selection(TIME_SLOTS, string="End Time", required=True)

class BoxCricketConfig(models.Model):
    _name = 'box.cricket.config'
    _description = 'Box Cricket Configuration'

    name = fields.Char(string="Name", required=True)
    lane_id = fields.Many2many(
        'product.product',
        string="Lane",
        domain="[('product_type', '=', 'lane_rental')]",
        required=True
    )
    is_publish = fields.Boolean("Publish")
    parent_id = fields.Many2one('product.template', string="Product")

    @api.constrains('lane_id')
    def _check_lane_selection(self):
        for record in self:
            lanes = record.lane_id.sorted(lambda l: l.id)
            if len(lanes) != 3:
                raise ValidationError("You must select  3 lanes.")

            lane_ids = [lane.id for lane in lanes]
            expected_ids = list(range(lane_ids[0], lane_ids[0] + 3))

            if lane_ids != expected_ids:
                raise ValidationError("Lanes must be selected in a continuous sequence.")
            existing_configs = self.env['box.cricket.config'].search([
                ('id', '!=', record.id),  # Exclude the current record
                ('lane_id', 'in', lane_ids)
            ])

            if existing_configs:
                raise ValidationError(
                    "One or more selected lanes are already assigned to another Box . Please select different lanes.")

class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _get_redirect_url(self, post=None):
        book_a_lane_url = "/book-a-lane"
        return book_a_lane_url



class ProductTemplate(models.Model):
        _inherit = 'product.template'

        is_box_cricket = fields.Boolean(string="Box Cricket")
        box_configuration_ids = fields.One2many('box.cricket.config', 'parent_id', string="Box Configuration")
        time_slot_ids = fields.One2many('time.slot', 'product_id', string="Time Slot")
        peak_time_ids = fields.One2many('product.peak.time', 'product_id', string="Peak Times")
        peak_price = fields.Float(string="Peak Price")
        extra_addons_ids = fields.One2many('extra.addons', 'product_addons_id', string="Extra Addons")

        morning_start_time = fields.Selection(
            TIME_SLOTS, string="Morning Start Time",
        )
        morning_end_time = fields.Selection(
            TIME_SLOTS, string= "Morning End Time",
        )
        morning_price = fields.Float(string="Morning Shift Price")

        evening_start_time = fields.Selection(
            TIME_SLOTS, string="Evening Start Time",
        )
        evening_end_time = fields.Selection(
            TIME_SLOTS, string="Evening End Time",
        )
        evening_price = fields.Float(string="Evening Shift Price")

        weekend_morning_price = fields.Float(string="Weekend Morning Price")

        weekend_evening_price = fields.Float(string="Weekend Evening Price")

        product_type = fields.Selection([
            ('lane_rental', 'Lane Rental'),
            ('subscription', 'Subscription'),
            ('addons', 'Add-ons'),
            ('proshops', 'Proshops')
        ], string="Product Type", required=True)

        validity_period = fields.Selection([
            ('month', 'Month'),
            ('year', 'Year')
        ], string="Validity Period", help="Applicable only for Subscription products")

        video_checkbox = fields.Boolean(string="Include Video", help="Applicable only for Add-ons")
        is_publish = fields.Boolean(string="Publish")



        @api.onchange('event_type')
        def _onchange_event_type(self):
            if self.event_type == 'daily':
                self.date_from = False
                self.date_to = False
            elif self.event_type == 'monthly':
                self.date = False


class Slot(models.Model):
    _name = 'product.slot'
    _description = 'Slot for Products'

    sale_id = fields.Many2one('sale.order', "Sale Order")
    product_id = fields.Many2one('product.product', string="Product", required=True)
    product_name = fields.Many2one('product.template', string="Product")
    lane_name = fields.Char("Lane")
    is_booked = fields.Boolean("Is Booked?")
    # Soft-lock expiry: slot is reserved but only blocks others until this time.
    # After expiry the cron will cancel the parent order and release the slot.
    reservation_expiry = fields.Datetime("Reservation Expiry")
    dayname = fields.Char("Day Name (Optional/ Required for Recurring)")
    user_id = fields.Many2one('res.users',"User")
    is_paid = fields.Boolean("Is Paid")



    event_type = fields.Selection([
        ('daily', 'Daily'),
        ('monthly', 'Monthly')
    ], string="Event Type", default='daily', required=True)

    date = fields.Date("Date")

    time_slot = fields.Selection([
        ('12:00 AM', '12:00 AM'), ('12:30 AM', '12:30 AM'),
        ('01:00 AM', '01:00 AM'), ('01:30 AM', '01:30 AM'),
        ('02:00 AM', '02:00 AM'), ('02:30 AM', '02:30 AM'),
        ('03:00 AM', '03:00 AM'), ('03:30 AM', '03:30 AM'),
        ('04:00 AM', '04:00 AM'), ('04:30 AM', '04:30 AM'),
        ('05:00 AM', '05:00 AM'), ('05:30 AM', '05:30 AM'),
        ('06:00 AM', '06:00 AM'), ('06:30 AM', '06:30 AM'),
        ('07:00 AM', '07:00 AM'), ('07:30 AM', '07:30 AM'),
        ('08:00 AM', '08:00 AM'), ('08:30 AM', '08:30 AM'),
        ('09:00 AM', '09:00 AM'), ('09:30 AM', '09:30 AM'),
        ('10:00 AM', '10:00 AM'), ('10:30 AM', '10:30 AM'),
        ('11:00 AM', '11:00 AM'), ('11:30 AM', '11:30 AM'),
        ('12:00 PM', '12:00 PM'), ('12:30 PM', '12:30 PM'),
        ('01:00 PM', '01:00 PM'), ('01:30 PM', '01:30 PM'),
        ('02:00 PM', '02:00 PM'), ('02:30 PM', '02:30 PM'),
        ('03:00 PM', '03:00 PM'), ('03:30 PM', '03:30 PM'),
        ('04:00 PM', '04:00 PM'), ('04:30 PM', '04:30 PM'),
        ('05:00 PM', '05:00 PM'), ('05:30 PM', '05:30 PM'),
        ('06:00 PM', '06:00 PM'), ('06:30 PM', '06:30 PM'),
        ('07:00 PM', '07:00 PM'), ('07:30 PM', '07:30 PM'),
        ('08:00 PM', '08:00 PM'), ('08:30 PM', '08:30 PM'),
        ('09:00 PM', '09:00 PM'), ('09:30 PM', '09:30 PM'),
        ('10:00 PM', '10:00 PM'), ('10:30 PM', '10:30 PM'),
        ('11:00 PM', '11:00 PM'), ('11:30 PM', '11:30 PM')
    ], string="Time Slot", required=True)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    selected_slots = fields.Text(string="Selected Slots")
    selected_addons = fields.Text(string="Selected Add-ons")
    # selected_slots_print = fields.Text(string="Selected Print")
    
    def _check_cart_is_ready_to_be_paid(self):
        if not self._is_cart_ready():
            raise ValidationError(_(
                "Your cart is not ready to be paid, please verify previous steps."
            ))

class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _get_redirect_url(self, post=None):
        book_a_lane_url = "/book-a-lane"
        return book_a_lane_url

class MembershipFrequency(models.Model):
    _name = 'membership.frequency'
    _description = 'Membership Frequency'

    name = fields.Char(string="Frequency Type", required=True)
    price = fields.Float(string="Price", required=True)
    subscription_id = fields.Many2one('member.subscription', string="Membership", ondelete='cascade')

class MemberSubscription(models.Model):
    _name = "member.subscription"
    _description = "Membership Subscription"

    name = fields.Char(string="Name", required=True)
    description = fields.Text(string="Description")
    price = fields.Float(string="Price")

    frequency_ids = fields.One2many('membership.frequency', 'subscription_id', string="Frequency Types")

    # Group Coaching
    group_coaching_monthly = fields.Boolean(string="Group Coaching (Monthly)")
    group_coaching_quarterly = fields.Boolean(string="Group Coaching (Quarterly)")
    group_coaching_half_yearly = fields.Boolean(string="Group Coaching (Half-Yearly)")
    group_coaching_not_applicable = fields.Boolean(string="Group Coaching (Not Applicable)")

    # Semi-Private
    semi_private_monthly = fields.Char(string="Semi-Private (Monthly)")
    semi_private_quarterly = fields.Char(string="Semi-Private (Quarterly)")
    semi_private_half_yearly = fields.Char(string="Semi-Private (Half-Yearly)")
    semi_private_not_applicable = fields.Boolean(string="Semi-Private (Not Applicable)")

    # 1:1 Coaching
    one_to_one_monthly = fields.Char(string="1:1 Coaching (Monthly)")
    one_to_one_quarterly = fields.Char(string="1:1 Coaching (Quarterly)")
    one_to_one_half_yearly = fields.Char(string="1:1 Coaching (Half-Yearly)")
    one_to_one_not_applicable = fields.Boolean(string="1:1 Coaching (Not Applicable)")

    # Bowling Machine
    bowling_machine_monthly = fields.Char(string="Bowling Machine (Monthly)")
    bowling_machine_quarterly = fields.Char(string="Bowling Machine (Quarterly)")
    bowling_machine_half_yearly = fields.Char(string="Bowling Machine (Half-Yearly)")
    bowling_machine_not_applicable = fields.Boolean(string="Bowling Machine (Not Applicable)")

    # Gym Access
    gym_access_monthly = fields.Char(string="Gym Access (Monthly)")
    gym_access_quarterly = fields.Char(string="Gym Access (Quarterly)")
    gym_access_half_yearly = fields.Char(string="Gym Access (Half-Yearly)")
    gym_access_not_applicable = fields.Boolean(string="Gym Access (Not Applicable)")

    # Lane Hours
    lane_hours_monthly = fields.Char(string="Lane Hours (Monthly)")
    lane_hours_quarterly = fields.Char(string="Lane Hours (Quarterly)")
    lane_hours_half_yearly = fields.Char(string="Lane Hours (Half-Yearly)")
    lane_hours_not_applicable = fields.Boolean(string="Lane Hours (Not Applicable)")


class OurTeams(models.Model):
    _name = "our.team"
    _description = "Our Teams"

    name = fields.Char(string="Name", required=True)
    description = fields.Text(string="Description")
    image = fields.Image(string="Image")
    coach_name = fields.Char("Coach Name")
    training_timing = fields.Char("Training Timing")
    age_group = fields.Char("Age Group")

class BoxCricketMatch(models.Model):
    _name = 'box.cricket.match'
    _description = 'Box Cricket Match'


    date = fields.Date(string='Match Date', required=True)
    time = fields.Float("Time")
    first_team_id = fields.Many2one('our.team', string='First Team', required=True)
    second_team_id = fields.Many2one('our.team', string='Second Team', required=True)

class BoxCricketPointsTable(models.Model):
    _name = 'box.cricket.points'
    _description = 'Box Cricket Points Table'

    team_id = fields.Many2one('our.team', string='Team', required=True)
    matches_played = fields.Integer(string='Matches Played', default=0)
    won = fields.Integer(string='Matches Won', default=0)
    lost = fields.Integer(string='Matches Lost', default=0)
    points = fields.Integer(string='Points', compute='_compute_points', store=True)

    @api.depends('won', 'lost')
    def _compute_points(self):
        for record in self:
            record.points = record.won * 2

class BoxCricketEvent(models.Model):
    _name = 'box.cricket.event'
    _description = 'Box Cricket Upcoming Events'

    name = fields.Char(string="Event Title", required=True)
    description = fields.Text(string="Event Description")
    features = fields.Text(string="Event Features")
    image_1 = fields.Image(string="Primary Image")
    image_2 = fields.Image(string="Secondary Image")


class GalleryImage(models.Model):
    _name = 'gallery.image'
    _description = 'Gallery Image'


    image = fields.Image(string="Upload Image")

# My Code
class CalendarEvent(models.Model):
    _inherit  = 'calendar.event'
    
    sales_order_id = fields.Many2one(
        comodel_name='sale.order',
        string="Related Sales Order",
        ondelete='cascade'
    )
class SalesOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """When an admin confirms the order, immediately mark all linked lane
        slots and addon reservations as booked + paid so they are blocked from
        double-booking by other users (who fall through the Stripe payment path)."""
        result = super().action_confirm()
        for order in self:
            slots = self.env['product.slot'].sudo().search([('sale_id', '=', order.id)])
            if slots:
                slots.write({'is_booked': True, 'is_paid': True})

            addons = self.env['extra.addons'].sudo().search([('sale_id', '=', order.id)])
            if addons:
                addons.write({'is_book': True, 'is_paid': True})
        return result


    def action_cancel(self):
        for order in self:
            # Find and delete associated calendar events
            events = self.env['calendar.event'].sudo().search([('sales_order_id', '=', order.id)])
            if events:
                events.unlink()

            # Reset lane slots so they become available again
            slots = self.env['product.slot'].sudo().search([('sale_id', '=', order.id)])
            if slots:
                slots.write({'is_booked': False, 'sale_id': False, 'is_paid': False})

            # Also release addon (bowling machine) reservations so they
            # become available for other users.
            addons = self.env['extra.addons'].sudo().search([('sale_id', '=', order.id)])
            if addons:
                addons.write({'is_book': False, 'is_paid': False})

        if any(order.locked for order in self):
            raise UserError(_("You cannot cancel a locked order. Please unlock it first."))
        cancel_warning = self._show_cancel_wizard()
        if cancel_warning:
            self.ensure_one()
            template_id = self.env['ir.model.data']._xmlid_to_res_id(
                'sale.mail_template_sale_cancellation', raise_if_not_found=False
            )
            lang = self.env.context.get('lang')
            template = self.env['mail.template'].browse(template_id)
            if template.lang:
                lang = template._render_lang(self.ids)[self.id]
            ctx = {
                'default_template_id': template_id,
                'default_order_id': self.id,
                'mark_so_as_canceled': True,
                'default_email_layout_xmlid': "mail.mail_notification_layout_with_responsible_signature",
                'model_description': self.with_context(lang=lang).type_name,
            }
            return {
                'name': ('Cancel %s', self.type_name),
                'view_mode': 'form',
                'res_model': 'sale.order.cancel',
                'view_id': self.env.ref('sale.sale_order_cancel_view_form').id,
                'type': 'ir.actions.act_window',
                'context': ctx,
                'target': 'new'
            }
        else:
            return self._action_cancel()

    def _cron_release_expired_reservations(self):
        """Scheduled action (every 5 min): cancel abandoned draft orders whose
        slot reservation has expired, releasing all slots + addons.
        Uses _action_cancel() directly to bypass the cancel wizard."""
        now = fields.Datetime.now()
        expired_slots = self.env['product.slot'].sudo().search([
            ('is_booked', '=', False),
            ('reservation_expiry', '!=', False),
            ('reservation_expiry', '<', now),
            ('sale_id', '!=', False),
        ])
        expired_orders = expired_slots.mapped('sale_id').filtered(
            lambda o: o.state == 'draft'
        )
        for order in expired_orders:
            # Inline cleanup (mirrors action_cancel for-loop) before state change
            slots = self.env['product.slot'].sudo().search([('sale_id', '=', order.id)])
            if slots:
                slots.write({'is_booked': False, 'sale_id': False, 'is_paid': False})
            addons = self.env['extra.addons'].sudo().search([('sale_id', '=', order.id)])
            if addons:
                addons.write({'is_book': False, 'is_paid': False})
            order.sudo()._action_cancel()

# --------
