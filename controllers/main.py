import math
import json
import re
from odoo import http, tools, _, SUPERUSER_ID, fields as odoo_fields
from odoo.http import request
from odoo.tools.json import scriptsafe as json_scriptsafe
from odoo.addons.auth_signup.controllers.main import AuthSignupHome as Home
from datetime import datetime, timedelta
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.portal.controllers.portal import CustomerPortal
import requests
import pytz
from datetime import datetime
class CustomerPortalInherit(CustomerPortal):
    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        values['is_admin'] = request.env.user.has_group('sales_team.group_sale_manager')  # Check if admin
        
        # Add slot count
        partner = request.env.user.partner_id
        Slot = request.env['product.slot']
        slot_count = Slot.sudo().search_count([
            '|',
            ('sale_id.partner_id', '=', partner.id),
            ('user_id', '=', request.env.user.id),
            ('is_booked', '=', True)
        ])
        values['slot_count'] = slot_count
        return values

    def _add_30_minutes(self, time_str):
        """Add 30 minutes to a time string and return formatted time"""
        try:
            time_obj = datetime.strptime(time_str, '%I:%M %p')
            new_time = time_obj + timedelta(minutes=30)
            return new_time.strftime('%I:%M %p')
        except:
            return time_str

    @http.route(['/my/slots'], type='http', auth="user", website=True)
    def portal_my_slots(self, **kwargs):
        user = request.env.user
        Slot = request.env['product.slot'].sudo()
        
        domain = [
            '|',
            ('sale_id.partner_id', '=', user.partner_id.id),
            ('user_id', '=', user.id),
            ('is_booked', '=', True)
        ]
        
        # 1. Fetch all slots
        slots = Slot.search(domain)
        
        # 2. Group by booking (sale_id + date + lane + product + status)
        grouped_slots = {}
        for slot in slots:
            # Create a unique key for grouping
            sale_name = slot.sale_id.name if slot.sale_id else 'N/A'
            key = (
                slot.sale_id.id or 0,
                slot.date,
                slot.lane_name or '',
                slot.product_id.id or 0,
                slot.is_booked
            )
            
            if key not in grouped_slots:
                grouped_slots[key] = {
                    'sale_id': slot.sale_id,
                    'date': slot.date,
                    'lane_name': slot.lane_name,
                    'product_id': slot.product_id,
                    'is_booked': slot.is_booked,
                    'time_slots': []
                }
            
            grouped_slots[key]['time_slots'].append(slot.time_slot)
            
        # 3. Process each group to merge continuous slots
        display_slots = []
        
        for key, group in grouped_slots.items():
            # Sort time slots chronologically
            def time_to_comparable(time_str):
                try:
                    return datetime.strptime(time_str, '%I:%M %p')
                except:
                    return datetime.strptime('12:00 AM', '%I:%M %p')
            
            sorted_times = sorted(group['time_slots'], key=time_to_comparable)
            
            if not sorted_times:
                continue
                
            # Iterate and merge
            current_start = sorted_times[0]
            current_end = self._add_30_minutes(current_start)
            
            for i in range(1, len(sorted_times)):
                next_time = sorted_times[i]
                
                # Check if next_time is contiguous with current_end
                # We need to compare strict equality of strings formatted as %I:%M %p
                if next_time == current_end:
                    # Extend current block
                    current_end = self._add_30_minutes(next_time)
                else:
                    # Gap detected, save current block and start new
                    display_slots.append({
                        'sale_id': group['sale_id'],
                        'date': group['date'],
                        'time_slot': f"{current_start} - {current_end}",
                        'lane_name': group['lane_name'],
                        'product_id': group['product_id'],
                        'is_booked': group['is_booked'],
                        'sort_date': group['date'],
                        'sort_time': time_to_comparable(current_start)
                    })
                    
                    current_start = next_time
                    current_end = self._add_30_minutes(current_start)
            
            # Append the last block
            display_slots.append({
                'sale_id': group['sale_id'],
                'date': group['date'],
                'time_slot': f"{current_start} - {current_end}",
                'lane_name': group['lane_name'],
                'product_id': group['product_id'],
                'is_booked': group['is_booked'],
                'sort_date': group['date'],
                'sort_time': time_to_comparable(current_start)
            })

        # 4. Final Sort
        display_slots.sort(key=lambda x: (x['sort_date'], x['sort_time']), reverse=True)
        
        values = {
            'slots': display_slots,
            'page_name': 'slots',
            'is_admin': user.has_group('sales_team.group_sale_manager')
        }
        return request.render('us_arena_website.portal_my_slots', values)

    @http.route(['/my/orders'], type='http', auth="user", website=True)
    def portal_my_orders(self, **kwargs):
        user = request.env.user
        SaleOrder = request.env['sale.order'].sudo()
        if user.has_group('sales_team.group_sale_manager'):
            orders = SaleOrder.search([])
        else:
             orders = SaleOrder.search([
            ('partner_id', '=', user.partner_id.id),
            ('invoice_status', '=', 'to invoice'),
            ('invoice_status', '=', 'invoiced')
        ])
  
        values = {
            'orders': orders,
            'is_admin': user.has_group('sales_team.group_sale_manager')
        }
        return request.render('sale.portal_my_orders', values)

class SummerCampController(http.Controller):

    @http.route('/summer_camp/register_and_add_to_cart', type='json', auth='public', website=True, csrf=False)
    def register_and_add_to_cart(self, **post):
        try:
            # Create Summer Camp registration record
            # Adjust field names if needed to match your model
            request.env['x_summer_cams'].sudo().create(post)

            # Add product 6483 to cart
            product_id = 6483
            order = request.website.sale_get_order(force_create=True)
            order._cart_update(product_id=product_id, add_qty=1)

            # Redirect to checkout
            return {'redirect_url': '/shop/checkout'}

        except Exception as e:
            return {'error': str(e)}
        
class WebsiteSaleInherit(WebsiteSale):

    @http.route('/shop/payment/validate', type='http', auth="user", website=True, sitemap=False)
    def shop_payment_validate(self, sale_order_id=None, slot_ids = None, **post):
        def send_confirmation_email(self,sale_order):
             # First, ensure the order has paid invoices
            is_paid = 1 #order.invoice_ids.filtered(lambda inv: inv.payment_state == 'in_payment')
            is_ewallet = 1 #if any(line.product_id.id == 6382 for line in order.order_line) else 0
            if is_paid or is_ewallet: 
                extra_addons = request.env['extra.addons'].sudo().search([
                    ('sale_id.state', 'in', ['sale', 'done']),  # only confirmed/paid orders
                    # ('sale_id', '=', order.id)
                    ('sale_id', '=', sale_order.id)
                ])

                for addons in extra_addons:
                    addons.is_book = True
                    addons.is_paid = True
            if not order:
                return request.redirect('/book-lanes')
            username = request.env.user.partner_id.name
            sale_order_table = f"""
                                 <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                                     <tr style="background-color: #e0e0e0; font-weight: bold;">
                                         <th>Order Reference</th>
                                         <th>Customer Name</th>
                                         <th>Order Date</th>
                                         <th>Total Amount</th>
                                     </tr>
                                     <tr>
                                         <td>{sale_order.name}</td>
                                         <td>{username}</td>
                                         <td>{sale_order.date_order}</td>
                                         <td>{sale_order.amount_total} {sale_order.currency_id.symbol}</td>
                                     </tr>
                                 </table>
                             """
    
            order_lines_table = """
                                 <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
                                     <tr style="background-color: #e0e0e0; font-weight: bold;">
                                         <th>Product</th>
                                         <th>Quantity</th>
                                         <th>Unit-Price</th>
                                         <th>Subtotal</th>
                                     </tr>
                               """
    
            for line in sale_order.order_line:
                order_lines_table += f"""
                                     <tr>
                                         <td>{line.product_id.name}</td>
                                         <td>{line.product_uom_qty}</td>
                                         <td>{line.price_unit} {sale_order.currency_id.symbol}</td>
                                         <td>{line.price_subtotal} {sale_order.currency_id.symbol}</td>
                                     </tr>
                                 """
    
            order_lines_table += "</table>"
            
            # Fetch slots associated with the order
            slots = request.env['product.slot'].sudo().search([('sale_id', '=', sale_order.id)])
            
            slot_lines_table = """
                                 <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
                                     <tr style="background-color: #e0e0e0; font-weight: bold;">
                                         <th>Date</th>
                                         <th>Lane</th>
                                         <th>Time</th>
                                     </tr>
                               """
            
            for slot in slots:
                slot_lines_table += f"""
                                     <tr>
                                         <td>{slot.date}</td>
                                         <td>{slot.lane_name}</td>
                                         <td>{slot.time_slot}</td>
                                     </tr>
                                 """
            
            slot_lines_table += "</table>"

            email_body = f"""
                                 <p>Dear {username},</p>
                                 <p>Your booking has been confirmed successfully!! Below are the details of your order:</p>
    
                                 <h3>Order Summary:</h3>
                                 {sale_order_table}

                                 <h3>Booking Details:</h3>
                                 {slot_lines_table}
    
                                 <h3>Order Details:</h3>
                                 {order_lines_table}
    
                                 <p>Thank you for choosing United Sports Arena!</p>
                                 <p>Best regards,</p>
                                 <p>United Sports Arena </p>
                             """
            print(request.env['ir.mail_server'].sudo().search([], limit=1))
            mail_server = request.env['ir.mail_server'].sudo().search([('name', '=', 'USArena - Invoice')], limit=1)
            email_from = f'United Sports Arena <{mail_server.smtp_user}>' if mail_server else ''
            email_to = '{},{}'.format(request.env.user.email, 'usarena.bookings@gmail.com')
    
            # Optional: set a reply-to address
            reply_to = 'contactus@unitedsportsarena.com'  
    
            mail_values = {
                'subject': 'Booking Confirmation - Your Order #' + sale_order.name,
                'body_html': email_body,
                'email_from': email_from,
                'email_to': email_to,
                'reply_to': reply_to
            }
    
            mail = request.env['mail.mail'].sudo().create(mail_values)
            mail.send()
        
        order = None
        if sale_order_id:
            order = request.env['sale.order'].sudo().browse(sale_order_id).exists()
            if order and order.id != request.session.get('sale_last_order_id'):
                order = None
        else:
            order = request.website.sale_get_order()
            if not order and 'sale_last_order_id' in request.session:
                last_order_id = request.session['sale_last_order_id']
                order = request.env['sale.order'].sudo().browse(last_order_id).exists()
        print(order,"order")
        if order and not any(line.product_id.categ_id.name == 'Lane Rentals' for line in order.order_line):
             super(WebsiteSaleInherit, self).shop_payment_validate(sale_order_id=sale_order_id, **post)
             return request.redirect('/my')
        slots = request.env['product.slot'].sudo().search([
            ('sale_id', '=', order.id)
        ])
        for slot in slots:
            slot.write({'is_booked': True,'is_paid': True})
        selected_sales_order = request.env['sale.order'].sudo().search([('id', '=', order.id)])
        selected_product_slot = request.env['product.slot'].sudo().search([('sale_id', '=', order.id)], limit=1)
        product_id = selected_product_slot.product_id
        product_details = request.env['product.product'].sudo().search([('id', '=', product_id.id)])
        product_tmpl_id = product_details.product_tmpl_id
        product_temp_details = request.env['product.template'].sudo().search([('id', '=', product_tmpl_id.id)])
        selected_slots = selected_sales_order.selected_slots
        CalendarEvent = request.env['calendar.event'].sudo()
        slots_to_process = json.loads(selected_slots)
        partner_id = selected_sales_order.partner_id
        dayname = selected_product_slot.dayname        
        rental_start_date = selected_sales_order.rental_start_date
        rental_end_date = selected_sales_order.rental_return_date

        difference = (rental_end_date - rental_start_date).days
        if difference == 1:
            slot_dates_times = []
            for slot in slots_to_process:
                if 'time' in slot:
                    selected_date_obj = datetime.strptime(slot['date'], "%Y-%m-%d")
                    start_time_str = slot['time']
                    time_format = "%I:%M %p" if 'AM' in start_time_str or 'PM' in start_time_str else "%H:%M"
                    start_time = datetime.strptime(start_time_str, time_format).time()
                    end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=30)).time()
                    end_time_str = end_time.strftime(time_format)
                    slot_time = datetime.strptime(start_time_str, time_format).time()
                    slot_datetime = datetime.combine(selected_date_obj, slot_time)
                    slot_dates_times.append(slot_datetime)

                start_time = datetime.strptime(start_time_str, "%I:%M %p").time()
                end_time = datetime.strptime(end_time_str, "%I:%M %p").time()

            # Group all slots to one event
            event_start = min(slot_dates_times) + timedelta(hours=4)
            event_end = max(slot_dates_times) + timedelta(minutes=30, hours=4)    
            event = CalendarEvent.with_context(tz='America/New_York').create({
                'name': f"{product_temp_details.name}: {partner_id.name} | {slot['lane_name']} Starts at {event_start}",
                'start': event_start,
                'stop': event_end,
                'partner_ids': [(4, partner_id.id)],
                'allday': False,
                'sales_order_id': order.id
            })
        else:
            while rental_start_date <= rental_end_date:
                if rental_start_date.strftime('%A').lower() == dayname.lower():
                    for slot in slots_to_process:
                        if 'time' in slot:
                            selected_date_obj = datetime.strptime(slot['date'], "%Y-%m-%d")
                            start_time_str = slot['time']
                            time_format = "%I:%M %p" if 'AM' in start_time_str or 'PM' in start_time_str else "%H:%M"
                            start_time = datetime.strptime(start_time_str, time_format).time()
                            end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=30)).time()
                            end_time_str = end_time.strftime(time_format)

                        start_time = datetime.strptime(start_time_str, "%I:%M %p").time()
                        end_time = datetime.strptime(end_time_str, "%I:%M %p").time()

                        event_date = rental_start_date.date()                    
                        event_start = datetime.combine(event_date, start_time)+ timedelta(hours=4)
                        event_end = datetime.combine(event_date, end_time)+ timedelta(hours=4)

                        if event_end < event_start:
                            event_end = event_end + timedelta(days=1)

                        event = CalendarEvent.with_context(tz='America/New_York').create({
                            'name': f"{product_temp_details.name}: {partner_id.name} | {slot['lane_name']} Starts at {event_start}",
                            'start': event_start,
                            'stop': event_end,
                            'partner_ids': [(4, partner_id.id)],
                            'allday': False,
                            'sales_order_id': order.id
                        })
                rental_start_date += timedelta(days=1)
        

        errors = self._get_shop_payment_errors(order) if order else []
        if errors:
            first_error = errors[0]
            error_msg = f"{first_error[0]}\n{first_error[1]}"
            raise ValidationError(error_msg)

        tx_sudo = order.get_portal_last_transaction() if order else order.env['payment.transaction']
        
        if not order or (order.amount_total and not tx_sudo):
            return request.redirect('/book-lanes')

        if order and not order.amount_total and not tx_sudo:
            if order.state != 'sale':
                order._validate_order()
            # >>> Call after successful payment <<<
            send_confirmation_email(self, order)
            request.website.sale_reset()
            return request.redirect(order.get_portal_url())
        
        request.website.sale_reset()
        if tx_sudo and tx_sudo.state == 'draft':
            return request.redirect('/book-lanes')
            
        return request.redirect('/book-lanes')

    @http.route(['/shop/confirmation'], type='http', auth="public", website=True, sitemap=False)
    def shop_payment_confirmation(self, **post):

        sale_order_id = request.session.get('sale_last_order_id')
        if sale_order_id:
            
            order = request.env['sale.order'].sudo().browse(sale_order_id)
            values = self._prepare_shop_payment_confirmation_values(order)
            return request.render("website_sale.confirmation", values)
        return request.redirect('/book-lanes')

    @http.route('/shop/payment', type='http', auth='user', website=True, sitemap=False)
    def shop_payment(self, order_id=None,slot_ids=None, **post):
        # Use order_id from the session if not passed explicitly
        if not order_id:
            order_id = request.session.get('sale_order_id')

        if not order_id:
            return request.redirect('/book-lanes')

        # Fetch the correct sale order using the order_id
        order_sudo = request.env['sale.order'].sudo().browse(int(order_id))

        if not order_sudo.exists():
            return request.redirect('/book-lanes')

        # Ensure proper order selection in session
        request.session['sale_order_id'] = order_sudo.id

        # Fetch payment render values
        render_values = self._get_shop_payment_values(order_sudo, **post)

        render_values['sale_order'] = order_sudo
        render_values['selected_slots'] = order_sudo.selected_slots or "No slot selected"
        render_values['selected_addons'] = order_sudo.selected_addons or "No Add-ons selected"

        slot_ids_str = request.httprequest.args.get('slot_ids', '')
        slot_ids_list = slot_ids_str.split(',') if slot_ids_str else []

        render_values['slot_ids'] = slot_ids_list

        if render_values['errors']:
            render_values.pop('payment_methods_sudo', '')
            render_values.pop('tokens_sudo', '')

        return request.render("website_sale.payment", render_values)

    @http.route(['/shop/cart/update'], type='http', auth="public", methods=['POST'], website=True)
    def cart_update(
            self, product_id, add_qty=1, set_qty=0, product_custom_attribute_values=None,
            no_variant_attribute_value_ids=None, **kwargs
    ):
        """This route is called when adding a product to cart (no options)."""
        product = request.env['product.product'].sudo().browse(int(product_id))
        
        if product.categ_id.name != 'Lane Rentals':
             return super(WebsiteSaleInherit, self).cart_update(
                product_id, add_qty, set_qty, product_custom_attribute_values,
                no_variant_attribute_value_ids, **kwargs
            )

        sale_order = request.website.sale_get_order(force_create=True)
        # for item in sale_order.order_line:
        #     item.price_unit = 1000
        if sale_order.state != 'draft':
            request.session['sale_order_id'] = None
            sale_order = request.website.sale_get_order(force_create=True)

        if product_custom_attribute_values:
            product_custom_attribute_values = json_scriptsafe.loads(product_custom_attribute_values)

        # old API, will be dropped soon with product configurator refactorings
        no_variant_attribute_values = kwargs.pop('no_variant_attribute_values', None)
        if no_variant_attribute_values and no_variant_attribute_value_ids is None:
            no_variants_attribute_values_data = json_scriptsafe.loads(no_variant_attribute_values)
            no_variant_attribute_value_ids = [
                int(ptav_data['value']) for ptav_data in no_variants_attribute_values_data
            ]

        sale_order._cart_update(
            product_id=int(product_id),
            add_qty=add_qty,
            set_qty=set_qty,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            **kwargs
        )

        request.session['website_sale_cart_quantity'] = sale_order.cart_quantity

        return request.redirect("/shop/payment")
    


    @http.route(['/shop/pricelist'], type='http', auth="public", website=True, sitemap=False)
    def pricelist(self, promo=None, **post):
        """
        Override default pricelist route to prevent empty promo codes 
        from being processed and changing prices
        """
        
        # Check if promo code is empty or just whitespace
        if promo is not None and not promo.strip():
            # Log the attempt for debugging
            print("Empty promo code submitted - rejecting")
            
            # Don't process - just redirect back to referrer
            redirect_url = request.httprequest.referrer or '/shop/payment'
            return request.redirect(redirect_url)
        
        # If promo code is valid (not empty), process it normally
        if promo and promo.strip():
            print(f"Valid promo code submitted: {promo}")
            return super(WebsiteSaleInherit, self).pricelist(promo=promo, **post)
        
        # No promo code provided at all - just redirect
        redirect_url = request.httprequest.referrer or '/shop/payment'
        return request.redirect(redirect_url)
    

    @http.route(['/shop/check_promo'], type='json', auth="public", website=True, csrf=False)
    def check_promo_code(self, promo=None, **post):
        """
        AJAX endpoint to validate promo code before submission
        Returns: {'valid': True/False, 'message': 'error message'}
        """
        if not promo or not promo.strip():
            return {
                'valid': False,
                'message': 'Please enter a discount code'
            }
        
        # Check if promo code exists in the system
        # This is a basic check - adjust based on your promo code system
        Pricelist = request.env['product.pricelist'].sudo()
        
        # Check in pricelist codes
        valid_code = Pricelist.search([
            ('code', '=', promo),
            ('active', '=', True)
        ], limit=1)
        
        if not valid_code:
            return {
                'valid': False,
                'message': f'The discount code "{promo}" is not valid'
            }
        
        return {
            'valid': True,
            'message': 'Valid discount code'
        }


def format_time_slot(time_slot):
    time_parts = time_slot.split(' ')
    hour, minute = time_parts[0].split(':')
    am_pm = time_parts[1]

    if len(hour) == 1:
        hour = '0' + hour

    return f'{hour}:{minute} {am_pm}'


from odoo.addons.web.controllers.home import Home

class CustomLogin(Home):
    
    # Override standard Odoo login route
    @http.route('/web/login', type='http', auth='public', website=True, sitemap=False)
    def web_login(self, redirect=None, **kw):
        # Check if user is already logged in
        if request.session.uid and not request.env.user._is_public():
            if not redirect:
                redirect = '/'  # or '/web' for backend
            return request.redirect(redirect)
        
        return super(CustomLogin, self).web_login(redirect=redirect, **kw)
    
    # Your custom login route
    @http.route('/login', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_login(self, **kw):
        # Check if user is already logged in
        if request.session.uid and not request.env.user._is_public():
            return request.redirect('/')
        
        return request.render('us_arena_website.login_template')

class CinderseasonHomeController(http.Controller):

    @http.route('/subscription', type='http', auth='public', website=True, methods=['GET'])
    def display_subscription(self, **kw):
        product = request.env['member.subscription'].sudo().search([])
        return request.render('us_arena_website.member_subscription', {
            'products': product,
        })

    @http.route('/coming-soon', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_coming(self, **kw):
        return request.render('us_arena_website.coming_soon')

    @http.route('/book-lanes', type='http', auth='public', website=True, methods=['GET'],csrf=False)
    def display_custom_template_mycart(self, **kw):
        Product = request.env['product.product'].sudo()

        # Get all lane rental products and filter unique templates
        all_lane_rental_products = Product.search([
            ('product_type', '=', 'lane_rental'),
        ])

        # Get unique product templates (only 1 variant per template)
        lane_rental_products = []
        seen_templates = set()

        for product in all_lane_rental_products:
            if product.product_tmpl_id.id not in seen_templates:
                seen_templates.add(product.product_tmpl_id.id)
                lane_rental_products.append(product)
                if len(lane_rental_products) >= 3:
                    break

        all_product_addons = Product.search([
            ('product_type', '=', 'addons'),
            ('is_publish', '=', True)
        ])

        product_addons = []
        seen_addon_templates = set()

        for product in all_product_addons:
            if product.product_tmpl_id.id not in seen_addon_templates:
                seen_addon_templates.add(product.product_tmpl_id.id)
                product_addons.append(product)
                if len(product_addons) >= 3:
                    break

        return request.render('us_arena_website.add_to_my_cart', {
            'products': lane_rental_products,
            'product_addons': product_addons
        })

    @http.route('/gallery', type='http', auth='public', website=True, csrf=False)
    def display_custom_template_gallery(self, **kw):
        images = request.env['gallery.image'].sudo().search([])
        return request.render('us_arena_website.gallery_temp', {'images': images})

    @http.route('/lane/cart', type='http', auth='public', website=True, methods=['POST'])
    def display_custom_template_lanecart(self, **kw):
        print(kw, "kwwwww")
        return request.render('us_arena_website.add_to_lane_cart')

    @http.route('/', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_home(self, **kw):

        return request.render('us_arena_website.home_page_template')

    @http.route('/contact-us', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_contact(self, **kw):

        return request.render('us_arena_website.contact_us_section')

    @http.route('/about', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_about(self, **kw):

        return request.render('us_arena_website.about_page_template')

    @http.route('/team', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_team(self, **kw):
        teams = request.env['our.team'].sudo().search([])  # Fetch all teams

        return request.render('us_arena_website.team_page_template', {"teams": teams})

    @http.route('/lane-rental', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_rental(self, **kw):
        products = request.env['product.template'].sudo().search([], limit=5)
        return request.render('us_arena_website.lane_rental_page_template', {
            'products': products
        })

    @http.route('/shop-page', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_shop(self, **kw):
        cricket_category = request.env['product.category'].sudo().search([('name', '=', 'Cricket')], limit=1)
        products = request.env['product.template'].sudo().search([

        ], limit=16)

        return request.render('us_arena_website.shop_page_template', {
            'products': products
        })

    @http.route('/events', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_league(self, **kw):
        points = request.env['box.cricket.points'].sudo().search([], order='points desc')
        events = request.env['box.cricket.event'].sudo().search([])

        return request.render('us_arena_website.league_page_template', {
            'events': events,
        })

    @http.route('/coaching', type='http', auth='public', website=True, methods=['GET'])
    def display_custom_template_coaching(self, **kw):
        return request.render('us_arena_website.coaching_page_template')

    # @http.route('/login', type='http', auth='public', website=True, methods=['GET'])
    # def display_custom_template_login(self, **kw):
    #     return request.render('us_arena_website.login_template')

    @http.route(['/shop/<model("product.template"):product>'], type='http', auth="public", website=True,
                )
    def product(self, product, category='', search='', **kwargs):
        if not request.website.has_ecommerce_access():
            return request.redirect('/web/login')
        product_id = request.env['product.product'].sudo().search([('name', '=', product.name)], limit=1)

        return request.render("us_arena_website.book_lane_template", {
            'product': product,
            'product_data': product_id
        })

    class ProductSlotController(http.Controller):
        @http.route('/my/add_to_cart', type='json', auth='public', csrf=False)
        def get_add_slots(self, product_id, **post):
            product_id = int(product_id)
            today = datetime.today().date()
            end_date = today + timedelta(days=3)

            slots = request.env['product.slot'].sudo().search([
                ('date', '>=', today),
                ('date', '<=', end_date),
                '|',
                ('is_booked', '=', 'True'),
                ('sale_id', '!=', False),
            ], order="date asc, time_slot asc")

            slot_dict = {}
            for slot in slots:
                slot_date = slot.date.strftime('%Y-%m-%d')
                if slot_date not in slot_dict:
                    slot_dict[slot_date] = []
                slot_dict[slot_date].append({
                    'slot_id': slot.id,
                    'slot_time': slot.time_slot,
                    'lane_name': slot.lane_name,
                    'product_name': slot.product_id.name,
                })
            return slot_dict

        @http.route('/date_change_cart', type='json', auth='public', csrf=False)
        def get_add_slots_date(self, product_id, selectedDate, **post):
            product_id = int(product_id)
            today = datetime.strptime(selectedDate, '%Y-%m-%d').date()
            end_date = today + timedelta(days=3)

            # slots = request.env['product.slot'].sudo().search([
            #     ('is_booked', '=', 'True'),
            #     ('date', '>=', today),
            #     ('date', '<=', end_date),
            # ])

            slots = request.env['product.slot'].sudo().search([
                ('date', '>=', today),
                ('date', '<=', end_date),
                '|',
                ('is_booked', '=', True),
                ('sale_id', '!=', False),
            ], order="date asc, time_slot asc")

            slot_dict = {}
            for slot in slots:
                slot_date = slot.date.strftime('%Y-%m-%d')
                if slot_date not in slot_dict:
                    slot_dict[slot_date] = []
                slot_dict[slot_date].append({
                    'slot_id': slot.id,
                    'slot_time': slot.time_slot,
                    'lane_name': slot.lane_name,
                    'product_name': slot.product_id.name,
                })
            return slot_dict

        from datetime import datetime
        import json
        from odoo import http
        from odoo.http import request
        from datetime import datetime

    class SlotController(http.Controller):

        @http.route('/check/extra-addons', type='json', auth='public', csrf=False)
        def check_addons(self, product_id, slots, **post):
            product_id = int(product_id)
            product = request.env['product.template'].sudo().search([('id', '=', product_id)], limit=1)
            product_variants = request.env['product.template.attribute.value'].sudo().search([('product_tmpl_id', '=', product_id)]).mapped('product_attribute_value_id').ids

            print(len(slots), len(product_variants))
            print(type(len(slots)), type(len(product_variants)))
            print(len(slots) // len(product_variants))
            # Extract all slot names into a list
            slot_names = [slot.get('lane_name','') for slot in slots]
            # Use a set to get unique slot names
            unique_slot_names = set(slot_names)
            # Get the count of unique slot names
            num_unique_slot_names = len(unique_slot_names)
            if not product:
                return {'error': 'Product not found'}
            if (len(slots) == 2) and (len(product_variants) == 1) or (num_unique_slot_names <= len(product_variants)):
                matching_addons = []
                for index, slot in enumerate(slots):
                    slot_time = slot.get('time', '')
                    slot_date = slot.get('date', '')
                    if index >= len(product_variants):
                        print(f"Skipping slot {index}, no matching product variant found.")
                        continue
                    extra_addons = request.env['extra.addons'].sudo().search([
                        ('product_addons_id', '=', product.id),
                        ('date', '=', slot_date),
                        ('time', '=', slot_time),
                        ('is_book', '=', True),
                        # FIX Bug 3: removed ('is_paid', '=', True) so that addons
                        # reserved but not yet paid still block new bookings.
                        ('product_addons_attribute_id', '=', product_variants[index])
                    ])
                    
                    for addon in extra_addons:
                        matching_addons.append({
                            'date': addon.date,
                            'time': addon.time,
                            'product_addons_id': addon.product_addons_id.id
                        })
                    print(matching_addons, "skedilaya here", index)
                if (len(matching_addons) == len(product_variants)):
                    
                    return {'available_extra_addons': matching_addons}
                else:
                    return {'available_extra_addons': []}
            else:
                return {'available_extra_addons_exceed': [f"The Machine you are trying to add has limited quantity of number {len(product_variants)}. Please select Slots according to it."]}

        # @http.route('/create_slot', type='json', auth='public', csrf=False)
        # def get_add_slots_create(self, product_id, selectedDate, slots, price, selectedAddonsDict, isRecurring, fromDate, toDate, dayname, noOfDays, **post):
            
        #     selected_slots = json.dumps(slots)
        #     selected_addons = json.dumps(selectedAddonsDict)
        #     slot_ids = []
        #     price = int(price)

        #     partner = request.env.user.partner_id

        #     # ✅ Check if discount system is enabled
        #     discount_enabled = request.env['subscription.discount.config'].sudo().is_discount_enabled()
            
        #     # Get active subscription
        #     active_subscription = request.env['user.subscription'].sudo().search([
        #         ('partner_id', '=', partner.id),
        #         ('status', '=', 'active')
        #     ], limit=1)

        #     # ✅ Only use subscription pricelist if discounts are enabled AND subscription exists
        #     if discount_enabled and active_subscription and active_subscription.pricelist_id:
        #         pricelist_id = active_subscription.pricelist_id.id
        #     else:
        #         # Use partner's default pricelist (no discount)
        #         pricelist_id = partner.property_product_pricelist.id
            
        #     if isRecurring:
        #         price = price * noOfDays
        #         from_date_obj = datetime.strptime(fromDate, "%Y-%m-%d")
        #         to_date_obj = datetime.strptime(toDate, "%Y-%m-%d")
        #         current_date_obj = from_date_obj
                
        #         # Check if slots are already booked for recurring booking
        #         while current_date_obj <= to_date_obj:
        #             if current_date_obj.strftime('%A').lower() == dayname.lower():
        #                 formatted_date = current_date_obj.strftime("%Y-%m-%d")
        #                 for slot in slots:
        #                     time_slot = slot.get('time', '')
        #                     lane_name = slot.get('lane_name', '')
        #                     product_id_int = int(product_id) if not isinstance(product_id, int) else product_id
                            
        #                     existing_slots = request.env['product.slot'].sudo().search([
        #                         ('date', '=', formatted_date),
        #                         ('time_slot', '=', time_slot),
        #                         ('lane_name', '=', lane_name),
        #                         ('product_id', '=', product_id_int),
        #                         ('is_booked', '=', True),
        #                         ('is_paid', '=', True)
        #                     ])
                            
        #                     if existing_slots:
        #                         return {
        #                             'status': 'error',
        #                             'message': f"The slot {time_slot} on {formatted_date} ({current_date_obj.strftime('%A')}) is already booked. Please select a different time or date."
        #                         }
        #             current_date_obj += timedelta(days=1)                    
        #         current_date_obj = from_date_obj
        #     else:
        #         selected_date_obj = datetime.strptime(selectedDate, "%Y-%m-%d")
        #         from_date_obj = selected_date_obj
        #         to_date_obj = selected_date_obj + timedelta(days=1)

        #     current_date_obj = from_date_obj
        #     product = request.env['product.product'].sudo().browse(int(product_id))
        #     partner_id = request.env.user.partner_id
            
        #     current_time = datetime.now().strftime('%H:%M:%S')
        #     rental_start_date = from_date_obj.strftime('%Y-%m-%d') + " " + current_time
        #     rental_return_date = to_date_obj.strftime('%Y-%m-%d') + " " + current_time
            

        #     # pricelist_id = active_subscription.pricelist_id.id if active_subscription else False
            
        #     # Create sale order with pricelist
        #     sale_order = request.env['sale.order'].sudo().create({
        #         'partner_id': partner_id.id,
        #         'date_order': selectedDate,
        #         'is_rental_order': True,
        #         'pricelist_id': pricelist_id or partner_id.property_product_pricelist.id,
        #         # ... rest of your fields ...
        #     })


        #     # Create sale order
        #     sale_order = {
        #         'partner_id': partner_id.id,
        #         'date_order': selectedDate,
        #         'is_rental_order': True,
        #         'rental_start_date': rental_start_date,
        #         'rental_return_date': rental_return_date,
        #         'selected_slots': json.dumps(slots or []),
        #         'selected_addons': json.dumps(selectedAddonsDict or {}),
        #         'pricelist_id': pricelist_id or partner_id.property_product_pricelist.id,
        #         'order_line': [(0, 0, {
        #             'product_id': product.id,
        #             'product_uom_qty': 1,
        #             'price_unit': int(price),
        #         })],
        #     }

        #     sale_order = request.env['sale.order'].sudo().create(sale_order)
            
        #     request.session['sale_order_id'] = sale_order.id
        #     request.session['sale_last_order_id'] = sale_order.id
            

        #     partner_id = request.env.user.partner_id
    
        #     # Check if user has active subscription and get their pricelist
        #     active_subscription = request.env['user.subscription'].sudo().search([
        #         ('partner_id', '=', partner_id.id),
        #         ('status', '=', 'active')
        #     ], limit=1)
            


        #     # Create slots
        #     if isRecurring:
        #         while current_date_obj <= to_date_obj:
        #             if current_date_obj.strftime('%A').lower() == dayname.lower():
        #                 formatted_date = current_date_obj.strftime("%Y-%m-%d")
        #                 for slot in slots:
        #                     time_slot = slot.get('time', '')
        #                     lane_name = slot.get('lane_name', '')
        #                     new_slot = request.env['product.slot'].create({
        #                         'product_name': product.product_tmpl_id.id,
        #                         'product_id': product_id,
        #                         'lane_name': lane_name,
        #                         'date': formatted_date,
        #                         'time_slot': time_slot,
        #                         'sale_id': sale_order.id,
        #                         'user_id': request.env.user.id,
        #                         'dayname': dayname,
        #                     })
        #                     slot_ids.append(new_slot.id)
        #             current_date_obj += timedelta(days=1)
        #     else:
        #         formatted_date = current_date_obj.strftime("%Y-%m-%d")
        #         for slot in slots:
        #             time_slot = slot.get('time', '')
        #             lane_name = slot.get('lane_name', '')
                    
        #             new_slot = request.env['product.slot'].create({
        #                 'product_name': product.product_tmpl_id.id,
        #                 'product_id': product_id,
        #                 'lane_name': lane_name,
        #                 'date': formatted_date,
        #                 'time_slot': time_slot,
        #                 'sale_id': sale_order.id,
        #                 'user_id': request.env.user.id,
        #             })
        #             slot_ids.append(new_slot.id)
            
        #     # Add extra addons
        #     for addon_id, addon_price in selectedAddonsDict.items():
        #         extra_addons_list = []
        #         for slot in slots:
        #             time_slot = slot.get('time', '')
        #             addon_product_attribute = request.env['product.template.attribute.value'].sudo().search([
        #                 ('product_tmpl_id', '=', int(addon_id))
        #             ], limit=1)
                    
        #             extra_addons_list.append((0, 0, {
        #                 'date': selectedDate,
        #                 'time': time_slot,
        #                 'sale_id': sale_order.id,
        #                 'product_addons_id': int(addon_id),
        #                 'is_book': True,
        #                 'product_addons_attribute_id': int(addon_product_attribute.product_attribute_value_id)
        #             }))

        #         addon_product = request.env['product.product'].sudo().search([
        #             ('product_tmpl_id', '=', int(addon_id))
        #         ], limit=1)
        #         addon_product_tmpl = addon_product.product_tmpl_id
        #         addon_product_tmpl.write({'extra_addons_ids': extra_addons_list})
                
        #         existing_line = sale_order.order_line.filtered(lambda line: line.product_id.id == addon_product.id)
        #         addon_qty = len(slots)
                
        #         if existing_line:
        #             existing_line.product_uom_qty += 1
        #         else:
        #             request.env['sale.order.line'].sudo().create({
        #                 'order_id': sale_order.id,
        #                 'product_id': addon_product.id,
        #                 'product_uom_qty': addon_qty / 2,
        #                 'price_unit': int(addon_price),
        #             })
            
        #     slot_ids_str = ','.join(map(str, slot_ids))
        #     user = request.env.user
        #     is_admin = user.has_group('base.group_system')
            
        #     if is_admin:
        #         # FIXED: Use proper Odoo web client URL format
        #         # Use the web client action to open the sale order form view
        #         base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        #         action_id = request.env.ref('sale.action_orders').id
                
        #         # Return URL that opens in web client (avoids CORS issues)
        #         sales_order_url = f"/web#id={sale_order.id}&view_type=form&model=sale.order&action={action_id}"
                
        #         return {
        #             'status': 'success',
        #             'redirect': sales_order_url
        #         }
        #     else:
        #         # For non-admin users, send confirmation email
        #         username = request.env.user.partner_id.name
                
        #         sale_order_table = f"""
        #             <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
        #                 <tr style="background-color: #e0e0e0; font-weight: bold;">
        #                     <th>Order Reference</th>
        #                     <th>Customer Name</th>
        #                     <th>Order Date</th>
        #                     <th>Total Amount</th>
        #                 </tr>
        #                 <tr>
        #                     <td>{sale_order.name}</td>
        #                     <td>{username}</td>
        #                     <td>{sale_order.date_order}</td>
        #                     <td>{sale_order.amount_total} {sale_order.currency_id.symbol}</td>
        #                 </tr>
        #             </table>
        #         """

        #         order_lines_table = """
        #             <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
        #                 <tr style="background-color: #e0e0e0; font-weight: bold;">
        #                     <th>Product</th>
        #                     <th>Quantity</th>
        #                     <th>Unit Price</th>
        #                     <th>Subtotal</th>
        #                 </tr>
        #         """

        #         for line in sale_order.order_line:
        #             order_lines_table += f"""
        #                 <tr>
        #                     <td>{line.product_id.name}</td>
        #                     <td>{line.product_uom_qty}</td>
        #                     <td>{line.price_unit} {sale_order.currency_id.symbol}</td>
        #                     <td>{line.price_subtotal} {sale_order.currency_id.symbol}</td>
        #                 </tr>
        #             """

        #         order_lines_table += "</table>"

        #         email_body = f"""
        #             <p>Dear {username},</p>
        #             <p>Your booking has been confirmed successfully. Below are the details of your order:</p>
        #             <h3>Order Summary:</h3>
        #             {sale_order_table}
        #             <h3>Order Details:</h3>
        #             {order_lines_table}
        #             <p>Thank you for choosing United Sports Arena!</p>
        #             <p>Best regards,</p>
        #             <p>United Sports Arena</p>
        #         """
                
        #         mail_server = request.env['ir.mail_server'].sudo().search([
        #             ('name', '=', 'USArena - Invoice')
        #         ], limit=1)
        #         email_from = mail_server.smtp_user if mail_server else ''
        #         email_to = request.env.user.email

        #         mail_values = {
        #             'subject': 'Booking Confirmation - Order ' + sale_order.name,
        #             'body_html': email_body,
        #             'email_from': email_from,
        #             'email_to': email_to,
        #         }

        #         # Uncomment to send email
        #         # mail = request.env['mail.mail'].sudo().create(mail_values)
        #         # mail.send()
                
        #         payment_url = f"/shop/payment?order_id={sale_order.id}&slot_ids={slot_ids_str}"
                
        #         return {
        #             'status': 'success',
        #             'redirect': payment_url
        #         }


        @http.route('/create_slot', type='json', auth='public', csrf=False)
        def get_add_slots_create(self, product_id, selectedDate, slots, price, selectedAddonsDict, isRecurring, fromDate, toDate, dayname, noOfDays, **post):
            
            today = fields.Date.today()
            selected_slots = json.dumps(slots)
            selected_addons = json.dumps(selectedAddonsDict)
            slot_ids = []
            price = int(price)

            partner = request.env.user.partner_id

            # Check if discount system is enabled
            discount_enabled = request.env['subscription.discount.config'].sudo().is_discount_enabled()

            # FIX: Use partner's computed field which correctly checks status='active' AND end_date >= today.
            # The previous search used only start_date/end_date date-range filters and omitted
            # status='active', so cancelled/expired subscriptions (or records without date fields)
            # could match — causing apply_subscription_discount_line() to be skipped entirely.
            active_subscription = partner.active_subscription_id

            print("active_subscription=======", active_subscription)
            user = request.env.user
            is_admin = user.has_group('base.group_system')
            # Calculate price adjustments (for recurring bookings)
            if isRecurring:
                price = price * noOfDays
                from_date_obj = datetime.strptime(fromDate, "%Y-%m-%d")
                to_date_obj = datetime.strptime(toDate, "%Y-%m-%d")
                current_date_obj = from_date_obj
                
                # Check if slots are already booked for recurring booking
                now = odoo_fields.Datetime.now()  # compute once for the whole check
                while current_date_obj <= to_date_obj:
                    if current_date_obj.strftime('%A').lower() == dayname.lower():
                        formatted_date = current_date_obj.strftime("%Y-%m-%d")
                        for slot in slots:
                            time_slot = slot.get('time', '')
                            lane_name = slot.get('lane_name', '')
                            product_id_int = int(product_id) if not isinstance(product_id, int) else product_id

                            # Soft-lock: block if confirmed/paid OR reserved and not yet expired.
                            existing_slots = request.env['product.slot'].sudo().search([
                                ('date', '=', formatted_date),
                                ('time_slot', '=', time_slot),
                                ('lane_name', '=', lane_name),
                                ('product_id', '=', product_id_int),
                                '|',
                                ('is_booked', '=', True),
                                '&',
                                    ('sale_id', '!=', False),
                                    '|',
                                    ('reservation_expiry', '=', False),
                                    ('reservation_expiry', '>=', now),
                            ])

                            if existing_slots:
                                return {
                                    'status': 'error',
                                    'message': f"The slot {time_slot} on {formatted_date} ({current_date_obj.strftime('%A')}) is already booked. Please select a different time or date."
                                }
                    current_date_obj += timedelta(days=1)
                current_date_obj = from_date_obj
            else:
                selected_date_obj = datetime.strptime(selectedDate, "%Y-%m-%d")
                from_date_obj = selected_date_obj
                to_date_obj = selected_date_obj + timedelta(days=1)

                # FIX Bug 2 (single-date): Check for conflicts before creating the order.
                # Previously there was NO check here at all for non-recurring bookings.
                formatted_date = selected_date_obj.strftime("%Y-%m-%d")
                now = odoo_fields.Datetime.now() # Moved outside the inner loop
                for slot in slots:
                    time_slot = slot.get('time', '')
                    lane_name = slot.get('lane_name', '')
                    product_id_int = int(product_id) if not isinstance(product_id, int) else product_id

                    existing_slots = request.env['product.slot'].sudo().search([
                        ('date', '=', formatted_date),
                        ('time_slot', '=', time_slot),
                        ('lane_name', '=', lane_name),
                        ('product_id', '=', product_id_int),
                        '|',
                        ('is_booked', '=', True),
                        '&',
                            ('sale_id', '!=', False),
                            '|',
                            ('reservation_expiry', '=', False),
                            ('reservation_expiry', '>=', now),
                    ])

                    if existing_slots:
                        return {
                            'status': 'error',
                            'message': f"The slot {time_slot} on {formatted_date} is already booked. Please select a different time."
                        }

            current_date_obj = from_date_obj
            product = request.env['product.product'].sudo().browse(int(product_id))
            partner_id = request.env.user.partner_id
            
            current_time = datetime.now().strftime('%H:%M:%S')
            rental_start_date = from_date_obj.strftime('%Y-%m-%d') + " " + current_time
            rental_return_date = to_date_obj.strftime('%Y-%m-%d') + " " + current_time
            
            # Use default pricelist (no discount at product level)
            pricelist_id = partner_id.property_product_pricelist.id
            
            # Create sale order
            sale_order = request.env['sale.order'].sudo().create({
                'partner_id': partner_id.id,
                'date_order': selectedDate,
                'is_rental_order': True,
                'rental_start_date': rental_start_date,
                'rental_return_date': rental_return_date,
                'selected_slots': json.dumps(slots or []),
                'selected_addons': json.dumps(selectedAddonsDict or {}),
                'pricelist_id': pricelist_id,
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': 1,
                    'price_unit': int(price),
                })],
            })
            
            request.session['sale_order_id'] = sale_order.id
            request.session['sale_last_order_id'] = sale_order.id

            # Create slots
            if isRecurring:
                while current_date_obj <= to_date_obj:
                    if current_date_obj.strftime('%A').lower() == dayname.lower():
                        formatted_date = current_date_obj.strftime("%Y-%m-%d")
                        for slot in slots:
                            time_slot = slot.get('time', '')
                            lane_name = slot.get('lane_name', '')
                            # Non-admin: stamp a 15-minute expiry so abandoned
                            # checkouts are automatically released by the cron.
                            expiry = None if is_admin else (
                                odoo_fields.Datetime.now() + timedelta(minutes=15)
                            )
                            new_slot = request.env['product.slot'].create({
                                'product_name': product.product_tmpl_id.id,
                                'product_id': product_id,
                                'lane_name': lane_name,
                                'date': formatted_date,
                                'time_slot': time_slot,
                                'sale_id': sale_order.id,
                                'user_id': request.env.user.id,
                                'dayname': dayname,
                                'is_booked': is_admin,
                                'is_paid': is_admin,
                                'reservation_expiry': expiry,
                            })
                            slot_ids.append(new_slot.id)
                    current_date_obj += timedelta(days=1)
            else:
                for slot in slots:
                    time_slot = slot.get('time', '')
                    lane_name = slot.get('lane_name', '')
                    # ✅ FIX: Use each slot's own date (sent from JS slotKey).
                    # Fallback to current_date_obj (== selectedDate) for single-date
                    # bookings where the slot date is the same as the picker date.
                    slot_date = slot.get('date') or current_date_obj.strftime("%Y-%m-%d")

                    expiry = None if is_admin else (
                        odoo_fields.Datetime.now() + timedelta(minutes=15)
                    )
                    new_slot = request.env['product.slot'].create({
                        'product_name': product.product_tmpl_id.id,
                        'product_id': product_id,
                        'lane_name': lane_name,
                        'date': slot_date,
                        'time_slot': time_slot,
                        'sale_id': sale_order.id,
                        'user_id': request.env.user.id,
                        'is_booked': is_admin,
                        'is_paid': is_admin,
                        'reservation_expiry': expiry,
                    })
                    slot_ids.append(new_slot.id)
            
            # Add extra addons
            for addon_id, addon_price in selectedAddonsDict.items():
                extra_addons_list = []

                addon_product_attribute = request.env['product.template.attribute.value'].sudo().search([
                    ('product_tmpl_id', '=', int(addon_id))
                ], limit=1)
                attr_value_id = int(addon_product_attribute.product_attribute_value_id)

                if isRecurring:
                    # FIX: Create one extra.addons entry per slot per recurring
                    # occurrence — previously only selectedDate was used, meaning
                    # every recurrence after the first was completely untracked.
                    recur_date_obj = datetime.strptime(fromDate, "%Y-%m-%d")
                    recur_end_obj = datetime.strptime(toDate, "%Y-%m-%d")
                    while recur_date_obj <= recur_end_obj:
                        if recur_date_obj.strftime('%A').lower() == dayname.lower():
                            recur_date_str = recur_date_obj.strftime("%Y-%m-%d")
                            for slot in slots:
                                time_slot = slot.get('time', '')
                                extra_addons_list.append((0, 0, {
                                    'date': recur_date_str,
                                    'time': time_slot,
                                    'sale_id': sale_order.id,
                                    'product_addons_id': int(addon_id),
                                    'is_book': True,
                                    'is_paid': is_admin,
                                    'product_addons_attribute_id': attr_value_id,
                                }))
                        recur_date_obj += timedelta(days=1)
                else:
                    # Single-date booking — use each slot's own date
                    for slot in slots:
                        time_slot = slot.get('time', '')
                        slot_date = slot.get('date') or selectedDate
                        extra_addons_list.append((0, 0, {
                            'date': slot_date,
                            'time': time_slot,
                            'sale_id': sale_order.id,
                            'product_addons_id': int(addon_id),
                            'is_book': True,
                            'is_paid': is_admin,
                            'product_addons_attribute_id': attr_value_id,
                        }))

                addon_product = request.env['product.product'].sudo().search([
                    ('product_tmpl_id', '=', int(addon_id))
                ], limit=1)
                addon_product_tmpl = addon_product.product_tmpl_id
                addon_product_tmpl.write({'extra_addons_ids': extra_addons_list})

                existing_line = sale_order.order_line.filtered(lambda line: line.product_id.id == addon_product.id)
                # qty = number of time slots per session (÷2 since slots come in pairs)
                addon_qty = len(slots)

                if existing_line:
                    existing_line.product_uom_qty += 1
                else:
                    request.env['sale.order.line'].sudo().create({
                        'order_id': sale_order.id,
                        'product_id': addon_product.id,
                        'product_uom_qty': addon_qty / 2,
                        'price_unit': int(addon_price),
                    })
            
            # ✅ NEW: Apply subscription discount to order total
            if discount_enabled and active_subscription:
                sale_order.apply_subscription_discount_line()
            
            slot_ids_str = ','.join(map(str, slot_ids))
            user = request.env.user
            is_admin = user.has_group('base.group_system')
            
            if is_admin:
                base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                action_id = request.env.ref('sale.action_orders').id
                sales_order_url = f"/web#id={sale_order.id}&view_type=form&model=sale.order&action={action_id}"
                
                return {
                    'status': 'success',
                    'redirect': sales_order_url
                }
            else:
                username = request.env.user.partner_id.name
                
                sale_order_table = f"""
                    <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                        <tr style="background-color: #e0e0e0; font-weight: bold;">
                            <th>Order Reference</th>
                            <th>Customer Name</th>
                            <th>Order Date</th>
                            <th>Total Amount</th>
                        </tr>
                        <tr>
                            <td>{sale_order.name}</td>
                            <td>{username}</td>
                            <td>{sale_order.date_order}</td>
                            <td>{sale_order.amount_total} {sale_order.currency_id.symbol}</td>
                        </tr>
                    </table>
                """

                order_lines_table = """
                    <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
                        <tr style="background-color: #e0e0e0; font-weight: bold;">
                            <th>Product</th>
                            <th>Quantity</th>
                            <th>Unit Price</th>
                            <th>Subtotal</th>
                        </tr>
                """

                for line in sale_order.order_line:
                    order_lines_table += f"""
                        <tr>
                            <td>{line.product_id.name}</td>
                            <td>{line.product_uom_qty}</td>
                            <td>{line.price_unit} {sale_order.currency_id.symbol}</td>
                            <td>{line.price_subtotal} {sale_order.currency_id.symbol}</td>
                        </tr>
                    """

                order_lines_table += "</table>"

                email_body = f"""
                    <p>Dear {username},</p>
                    <p>Your booking has been confirmed successfully. Below are the details of your order:</p>
                    <h3>Order Summary:</h3>
                    {sale_order_table}
                    <h3>Order Details:</h3>
                    {order_lines_table}
                    <p>Thank you for choosing United Sports Arena!</p>
                    <p>Best regards,</p>
                    <p>United Sports Arena</p>
                """
                
                payment_url = f"/shop/payment?order_id={sale_order.id}&slot_ids={slot_ids_str}"
                
                return {
                    'status': 'success',
                    'redirect': payment_url
                }

        @http.route('/get_slot_prices', type='json', auth='public', methods=['POST'])
        def get_slot_prices(self, product_id):
            if product_id:
                product_rec = request.env['product.product'].sudo().browse(int(product_id))
                product = request.env['product.template'].sudo().search([('name', '=', product_rec.name)], limit=1)
                return {
                    'morning_start_time': product.morning_start_time,
                    'morning_end_time': product.morning_end_time,
                    'evening_start_time': product.evening_start_time,
                    'evening_end_time': product.evening_end_time,
                    'morning_price': product.morning_price,
                    'evening_price': product.evening_price,
                    'weekend_morning_price': product.weekend_morning_price,
                    'weekend_evening_price': product.weekend_evening_price,
                }



        @http.route('/get_slot_prices_and_variants', type='json', auth='public', methods=['POST'])
        def get_slot_prices_and_variants(self, product_id, selected_date=None):
            box_configs = request.env['box.cricket.config'].sudo().search([])
            box_data = {}
            published_lanes = []

            for box in box_configs:
                box_name = box.name
                product_name = box.parent_id.name

                lanes = [
                    f"{lane.name}, {lane.default_code or lane.display_name}"
                    for lane in box.lane_id
                ]

                box_data[box_name] = {
                    "product": product_name,
                    "lanes": lanes,
                }

                if box.is_publish:
                    published_lanes.append(box_name)

            if product_id:
                product_rec = request.env['product.product'].sudo().browse(int(product_id))
                product_template = product_rec.product_tmpl_id

                time_slots = product_template.time_slot_ids

                slot_data = {}
                for slot in time_slots:
                    slot_data[slot.days] = {
                        'morning_start_time': slot.morning_start_time,
                        'morning_end_time': slot.morning_end_time,
                        'evening_start_time': slot.evening_start_time,
                        'evening_end_time': slot.evening_end_time,
                        'morning_price': slot.morning_price,
                        'evening_price': slot.evening_price
                    }

                variants = product_template.product_variant_ids.sudo().mapped(lambda v: {
                    'id': v.id,
                    'name': v.product_template_attribute_value_ids.mapped('product_attribute_value_id.name')[0]
                    if v.product_template_attribute_value_ids else v.name
                })
                
                # ✅ Fetch booked slots - CRITICAL: Only confirmed/paid ones
                booked_slots_data = []
                if selected_date:
                    # ✅ Use sudo() to ensure we get all booked slots regardless of user
                    booked_slots = request.env['product.slot'].sudo().search([
                        ('product_id', '=', int(product_id)),
                        ('date', '=', selected_date),
                        ('is_booked', '=', True),
                        # ('is_paid', '=', True),
                    ])
                    
                    # ✅ Log for debugging
                    # _logger.info(f"Found {len(booked_slots)} booked slots for date {selected_date}")
                    
                    for slot in booked_slots:
                        # _logger.info(f"Booked slot: {slot.lane_name} - {slot.time_slot} - is_booked: {slot.is_booked} - is_paid: {slot.is_paid}")
                        booked_slot_data = {
                            'date': slot.date,
                            'time': slot.time_slot,
                            'lane_name': slot.lane_name,
                            'product_id': slot.product_id.id,
                        }

                        # Check if user is admin (superuser or system admin)
                        if request.env.user.has_group('base.group_system'):
                            sale_order = slot.sale_id
                            if sale_order and sale_order.partner_id:
                                booked_slot_data['customer_name'] = sale_order.partner_id.name

                        booked_slots_data.append(booked_slot_data)
                # Fetch peak pricing config
                peak_time_ids = product_template.peak_time_ids
                peak_price = product_template.peak_price

                peak_slots = []
                for pt in peak_time_ids:
                    peak_slots.append({
                        'day': pt.days,
                        'start_time': pt.start_time,
                        'end_time': pt.end_time
                    })

                return {
                    'slot_data': slot_data,
                    'variants': variants,
                    'box_data': box_data,
                    'published_lanes': published_lanes,
                    'booked_slots': booked_slots_data,
                    'peak_slots': peak_slots,
                    'peak_price': peak_price,
                }


from odoo import http
from odoo.http import request


class CartUpdateController(http.Controller):

    @http.route('/update_cart', type='json', auth='public', methods=['POST'], website=True)
    def update_cart(self, product_id, add_qty, price):
        product_id = int(product_id)
        add_qty = int(add_qty)
        price = float(price)

        order = request.website.sale_get_order(force_create=True)

        order_line = order.order_line.filtered(lambda line: line.product_id.id == product_id)

        if order_line:
            new_qty = order_line.product_uom_qty + add_qty
            order_line.write({'product_uom_qty': new_qty, 'price_unit': price})
            return {'success': True, 'message': f"Updated quantity to {new_qty}!"}
        else:
            product = request.env['product.product'].browse(product_id)
            order.write({
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': add_qty,
                    'price_unit': price,
                })]
            })
            return {'success': True, 'message': "Product added to cart successfully!"}


class AuthSignUpRecaptchaValidation(Home):
    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False)
    def web_auth_signup(self, *args, **kw):
        if request.httprequest.method == 'POST':
            client_key = kw.get('g-recaptcha-response')
            secret_key = '6LfpHIcrAAAAAN1md4CvqaBfyWDLAnrWtMu1i-Fj'  # replace with your secret key

            captcha_data = {
                'secret': secret_key,
                'response': client_key
            }
            r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=captcha_data)
            response = json.loads(r.text)
            
            # check success and score
            verify = response.get('success') and response.get('score', 0) >= 0.5

            if not verify:
                values = request.params.copy()
                values['error'] = _("Captcha verification failed. Please try again.")
                return request.render('auth_signup.signup', values)

        return super(AuthSignUpRecaptchaValidation, self).web_auth_signup(*args, **kw)
    
class AuthFormsRecaptchaValidation(http.Controller):
    @http.route('/web/recaptcha-verification', type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def webreCaptchaVerification(self, **post):
        client_key = post.get('g-recaptcha-response')
        secret_key = '6LfpHIcrAAAAAN1md4CvqaBfyWDLAnrWtMu1i-Fj'  # move to config in production
        print("here")
        captcha_data = {
            'secret': secret_key,
            'response': client_key
        }
        r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=captcha_data)
        response = r.json()

        verified = response.get('success') and response.get('score', 0) >= 0.5

        if not verified:
            return request.make_response(
                json.dumps({'error': True, 'message': _("Captcha verification failed. Please try again.")}),
                headers=[('Content-Type', 'application/json')]
            )
        else:
            return request.make_response(
                json.dumps({'success': True, 'message': "Captcha verified"}),
                headers=[('Content-Type', 'application/json')]
            )


from odoo import models, fields, api

import logging

from odoo import http, fields
from odoo.http import request
import stripe
_logger = logging.getLogger(__name__)

class SubscriptionController(http.Controller):
    
    def _get_subscription_price(self, subscription_type):
        """Get subscription price from system parameters"""
        ICP = request.env['ir.config_parameter'].sudo()
        price_key = f'{subscription_type}_price'
        price = ICP.get_param(price_key)
        
        # Fallback: try to get from first active subscription of this type
        if not price:
            sub = request.env['user.subscription'].sudo().search([
                ('subscription_type', '=', subscription_type)
            ], limit=1)
            if sub:
                price = sub.price
        
        return float(price) if price else 0.0
    
    @http.route('/subscription/plans', type='http', auth='public', website=True)
    def subscription_plans(self, error=None, **kw):
        """Display subscription plans with group-based exclusivity logic"""

        user = request.env.user
        is_logged_in = not user._is_public()

        # Build a map of group_id -> active subscription for the logged-in user
        # Key: group_id (int or None), Value: user.subscription record
        active_subs_by_group = {}   # {group_id: subscription_record}
        active_sub_types = set()     # set of subscription_type strings that are active
        has_any_active = False

        if is_logged_in:
            today = request.env['ir.fields.date'].today() if False else fields.Date.today()
            active_subs = request.env['user.subscription'].sudo().search([
                ('partner_id', '=', user.partner_id.id),
                ('status', '=', 'active'),
            ])
            for sub in active_subs:
                if sub.end_date and sub.end_date >= today:
                    has_any_active = True
                    active_sub_types.add(sub.subscription_type)
                    gid = sub.group_id.id if sub.group_id else None
                    active_subs_by_group[gid] = sub

        # Get discount config
        discount_config = request.env['subscription.discount.config'].sudo().get_active_config()

        # Fetch group assignments from the admin-level type config (not per-user records)
        sub_type_group_map = request.env['subscription.type.config'].sudo().get_type_group_map()
        # sub_type_group_map: {subscription_type: group_id} e.g. {'subscription_a': 3, 'subscription_b': 3}

        subscription_types = [
            {'type': 'subscription_a'},
            {'type': 'subscription_b'},
            {'type': 'subscription_c'},
        ]

        # Stripe API key
        provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'stripe')
        ], limit=1)

        stripe.api_key = provider.stripe_secret_key

        plans = []

        for sub_type in subscription_types:
            plan = sub_type.copy()

            # Get Stripe product ID from system parameters
            param_key = f"stripe_{plan['type']}_product_id"
            product_id = request.env['ir.config_parameter'].sudo().get_param(param_key)

            if product_id:
                try:
                    product = stripe.Product.retrieve(product_id)
                    prices = stripe.Price.list(product=product_id, active=True)

                    if prices.data:
                        price = prices.data[0]
                        plan['price'] = price['unit_amount'] / 100.0
                        plan['currency'] = price['currency'].upper()
                        plan['interval'] = price.get('recurring', {}).get('interval', 'one-time')
                    else:
                        plan['price'] = 0.0
                        plan['currency'] = 'USD'
                        plan['interval'] = 'month'

                    plan['name'] = product.get('name')

                except Exception as e:
                    plan['name'] = "Stripe Error"
                    plan['price'] = 0.0
                    plan['interval'] = "-"
                    plan['currency'] = ""

            plan.setdefault('name', 'Unknown Plan')
            plan.setdefault('price', 0.0)
            plan.setdefault('currency', 'USD')
            plan.setdefault('interval', 'month')

            # Discount logic (unchanged)
            if discount_config:
                discounts = discount_config.get_discounts_for_subscription(plan['type'])
                plan['lane_discount'] = discounts.get('lane_rental_discount', 0)
                plan['merch_discount'] = discounts.get('merchandise_discount', 0)
            else:
                if plan['type'] == 'subscription_a':
                    plan['lane_discount'] = 5
                    plan['merch_discount'] = 5
                elif plan['type'] == 'subscription_b':
                    plan['lane_discount'] = 10
                    plan['merch_discount'] = 10
                elif plan['type'] == 'subscription_c':
                    plan['lane_discount'] = 15
                    plan['merch_discount'] = 20

            # --- Group-based conflict detection ---
            plan_group_id = sub_type_group_map.get(plan['type'])  # int or None
            plan['group_id'] = plan_group_id

            # This user already has THIS exact plan active
            plan['has_active'] = plan['type'] in active_sub_types

            # This user has a DIFFERENT plan in the SAME group (conflict)
            same_group_conflict_sub = None
            if not plan['has_active'] and plan_group_id is not None:
                same_group_conflict_sub = active_subs_by_group.get(plan_group_id)
            plan['same_group_conflict'] = bool(same_group_conflict_sub)
            plan['conflicting_sub_type'] = (
                same_group_conflict_sub.subscription_type if same_group_conflict_sub else None
            )
            plan['conflicting_sub_name'] = (
                same_group_conflict_sub.subscription_type_display if same_group_conflict_sub else None
            )

            # No conflict: different group (or no group) AND not already active
            plan['can_add'] = (
                not plan['has_active']
                and not plan['same_group_conflict']
            )

            plans.append(plan)

        values = {
            'plans': plans,
            'is_logged_in': is_logged_in,
            'has_any_active': has_any_active,
            'error': error,
        }

        return request.render('us_arena_website.member_subscription', values)

        @http.route('/my_subscription', type='http', auth='user', website=True)
        def my_subscription(self, **kw):
            """Display user's subscription page"""
            user = request.env.user
            partner = user.partner_id
            
            subscription = request.env['user.subscription'].sudo().search([
                ('partner_id', '=', partner.id)
            ], order='create_date desc', limit=1)
            
            values = {
                'user': user,
                'partner': partner,
                'subscription': subscription,
            }
            
            return request.render('us_arena_website.my_subscription_template', values)
    
    @http.route('/subscription/checkout', type='http', auth='user', website=True)
    def subscription_checkout(self, subscription_type='subscription_a', **kw):
        """Subscription checkout page with Stripe"""
        import stripe
        
        user = request.env.user
        partner = user.partner_id
        
        valid_types = ['subscription_a', 'subscription_b', 'subscription_c']
        if subscription_type not in valid_types:
            subscription_type = 'subscription_a'
        
        # Check if user already has an active subscription IN THE SAME GROUP
        # - If so, redirect to 'my_subscription' (they should use the upgrade flow)
        # - If different group, allow checkout (multi-group stacking)
        today = fields.Date.today()
        existing_active_subs = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'active'),
        ])
        existing_active_subs = existing_active_subs.filtered(
            lambda s: s.end_date and s.end_date >= today
        )

        # Look up group for requested type via admin type config
        requested_group_id = request.env['subscription.type.config'].sudo().get_group_for_type(
            subscription_type
        )

        for sub in existing_active_subs:
            if sub.subscription_type == subscription_type:
                # Already has this exact plan
                return request.redirect('/my_subscription')
            sub_group_id = request.env['subscription.type.config'].sudo().get_group_for_type(
                sub.subscription_type
            )
            if requested_group_id and sub_group_id == requested_group_id:
                # Different plan, same group — redirect to upgrade flow
                return request.redirect(
                    f'/subscription/upgrade?new_subscription_type={subscription_type}'
                )
        # Different group (or no group) — allow fresh checkout

        # Check for cancelled subscription
        cancelled_sub = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'cancelled')
        ], limit=1)
        
        # Get Stripe provider
        stripe_provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'stripe'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        if not stripe_provider:
            return request.render('website.404', {
                'status_code': 500,
                'status_message': 'Stripe payment is not enabled. Please contact administrator.'
            })
        
        publishable_key = stripe_provider.stripe_publishable_key
        if not publishable_key:
            return request.render('website.404', {
                'status_code': 500,
                'status_message': 'Stripe publishable key is missing. Please configure Stripe properly.'
            })
        
        # Get system parameters
        ICP = request.env['ir.config_parameter'].sudo()
        
        # Map subscription type to product parameter key
        product_param_map = {
            'subscription_a': 'stripe_subscription_a_product_id',
            'subscription_b': 'stripe_subscription_b_product_id',
            'subscription_c': 'stripe_subscription_c_product_id',
        }
        
        stripe_product_id = ICP.get_param(product_param_map[subscription_type])
        
        if not stripe_product_id:
            return request.render('website.404', {
                'status_code': 500,
                'status_message': f'Stripe product ID for {subscription_type} is not configured.'
            })
        
        # Subscription names
        subscription_names = {
            'subscription_a': 'Membership A',
            'subscription_b': 'Membership B',
            'subscription_c': 'Membership C',
        }
        
        # Default values
        subscription_price = 20.00
        stripe_price_id = None
        currency = 'USD'
        
        # Fetch the highest price for this product from Stripe
        try:
            stripe.api_key = stripe_provider.stripe_secret_key
            
            # Get all active prices for this product
            prices_list = stripe.Price.list(
                product=stripe_product_id,
                active=True,
                limit=100
            )
            
            if prices_list.data:
                # Filter for recurring monthly prices
                monthly_prices = [
                    p for p in prices_list.data 
                    if p.recurring and p.recurring.interval == 'month' and p.unit_amount
                ]
                
                if monthly_prices:
                    # Get the highest price
                    highest_price = max(monthly_prices, key=lambda p: p.unit_amount)
                    subscription_price = highest_price.unit_amount / 100
                    stripe_price_id = highest_price.id
                    currency = highest_price.currency.upper()
                    
                    _logger.info(f"Checkout: Selected highest price ${subscription_price} (ID: {stripe_price_id}) for {subscription_type}")
                else:
                    _logger.warning(f"No monthly prices found for product {stripe_product_id}")
            else:
                _logger.warning(f"No prices found for product {stripe_product_id}")
                
        except Exception as e:
            _logger.error(f"Failed to fetch Stripe prices for checkout: {str(e)}")
            return request.render('website.404', {
                'status_code': 500,
                'status_message': f'Failed to load subscription pricing. Please try again later.'
            })
        
        if not stripe_price_id:
            return request.render('website.404', {
                'status_code': 500,
                'status_message': f'No valid pricing found for this subscription.'
            })
        
        values = {
            'user': user,
            'partner': partner,
            'subscription_type': subscription_type,
            'subscription_name': subscription_names.get(subscription_type, 'Membership'),
            'subscription_price': subscription_price,
            'currency': currency,
            'stripe_publishable_key': publishable_key,
            'stripe_price_id': stripe_price_id,
            'is_test_mode': stripe_provider.state == 'test',
            'is_reactivation': bool(cancelled_sub),
        }
        
        return request.render('us_arena_website.subscription_checkout_template', values)
    
    @http.route('/subscription/create_stripe', type='json', auth='user', csrf=False)
    def create_stripe_subscription(self, payment_method_id, subscription_type='subscription_a', stripe_price_id=None, **kw):
        """Create Stripe subscription and local subscription record"""
        from datetime import timedelta
        import stripe
        
        user = request.env.user
        partner = user.partner_id
        
        valid_types = ['subscription_a', 'subscription_b', 'subscription_c']
        if subscription_type not in valid_types:
            subscription_type = 'subscription_a'
        
        try:
            stripe_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'stripe'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not stripe_provider:
                return {
                    'status': 'error',
                    'message': 'Stripe is not configured or enabled'
                }
            
            stripe.api_key = stripe_provider.stripe_secret_key
            
            # If stripe_price_id is not provided, fetch it from the product
            if not stripe_price_id:
                ICP = request.env['ir.config_parameter'].sudo()
                
                # Map subscription type to product parameter key
                product_param_map = {
                    'subscription_a': 'stripe_subscription_a_product_id',
                    'subscription_b': 'stripe_subscription_b_product_id',
                    'subscription_c': 'stripe_subscription_c_product_id',
                }
                
                stripe_product_id = ICP.get_param(product_param_map[subscription_type])
                
                if not stripe_product_id:
                    return {
                        'status': 'error',
                        'message': f'Stripe product ID for {subscription_type} is not configured'
                    }
                
                # Fetch the highest price for this product
                try:
                    prices_list = stripe.Price.list(
                        product=stripe_product_id,
                        active=True,
                        limit=100
                    )
                    
                    if prices_list.data:
                        # Filter for recurring monthly prices
                        monthly_prices = [
                            p for p in prices_list.data 
                            if p.recurring and p.recurring.interval == 'month' and p.unit_amount
                        ]
                        
                        if monthly_prices:
                            # Get the highest price
                            highest_price = max(monthly_prices, key=lambda p: p.unit_amount)
                            stripe_price_id = highest_price.id
                            _logger.info(f"Selected highest price: {stripe_price_id} (${highest_price.unit_amount/100})")
                        else:
                            return {
                                'status': 'error',
                                'message': 'No valid monthly pricing found for this subscription'
                            }
                    else:
                        return {
                            'status': 'error',
                            'message': 'No pricing found for this subscription'
                        }
                except Exception as e:
                    _logger.error(f"Failed to fetch prices: {str(e)}")
                    return {
                        'status': 'error',
                        'message': 'Failed to load subscription pricing'
                    }
            
            # Create or retrieve Stripe customer
            stripe_customer_id = partner.stripe_customer_id if hasattr(partner, 'stripe_customer_id') and partner.stripe_customer_id else None
            
            if not stripe_customer_id:
                customer = stripe.Customer.create(
                    email=partner.email,
                    name=partner.name,
                )
                stripe_customer_id = customer.id
                partner.sudo().write({'stripe_customer_id': stripe_customer_id})
            
            # Attach payment method to customer
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=stripe_customer_id,
            )
            
            # Set as default payment method
            stripe.Customer.modify(
                stripe_customer_id,
                invoice_settings={
                    'default_payment_method': payment_method_id,
                },
            )
            
            # Create Stripe subscription with the correct price ID
            subscription = stripe.Subscription.create(
                customer=stripe_customer_id,
                items=[{
                    'price': stripe_price_id,  # Use the fetched or provided price ID
                }],
                payment_settings={
                    'payment_method_types': ['card'],
                    'save_default_payment_method': 'on_subscription',
                },
                expand=['latest_invoice.payment_intent'],
                metadata={
                    'subscription_type': subscription_type,
                    'partner_id': partner.id,
                }
            )
            
            _logger.info(f"Stripe subscription created: {subscription.id} with status: {subscription.status}")
            
            invoice = subscription.latest_invoice
            
            if subscription.status == 'active':
                today = fields.Date.today()
                
                # Get discount configuration
                config = request.env['subscription.discount.config'].sudo().get_active_config()
                lane_discount = 0
                merch_discount = 0
                
                if config:
                    discounts = config.get_discounts_for_subscription(subscription_type)
                    lane_discount = discounts.get('lane_rental_discount', 0)
                    merch_discount = discounts.get('merchandise_discount', 0)
                
                # Get the actual price from the Stripe subscription
                # Retrieve the price object to get the amount
                try:
                    stripe_price_obj = stripe.Price.retrieve(stripe_price_id)
                    subscription_price = stripe_price_obj.unit_amount / 100 if stripe_price_obj.unit_amount else 20.00
                except Exception as e:
                    _logger.warning(f"Failed to retrieve price, using default: {str(e)}")
                    subscription_price = 20.00
                
                # Create local subscription record
                subscription_record = request.env['user.subscription'].sudo().create({
                    'user_id': user.id,
                    'partner_id': partner.id,
                    'subscription_type': subscription_type,
                    'price': subscription_price,
                    'status': 'active',
                    'start_date': today,
                    'end_date': today + timedelta(days=31),
                    'next_billing_date': today + timedelta(days=31),
                    'stripe_subscription_id': subscription.id,
                    'stripe_customer_id': stripe_customer_id,
                    'stripe_price_id': stripe_price_id,
                    'gym_access': True,
                    'lane_rental_discount': lane_discount,
                    'merchandise_discount': merch_discount,
                })
                
                _logger.info(f"Local subscription created: {subscription_record.id}")
                
                # Send confirmation email
                try:
                    self._send_subscription_confirmation_email(subscription_record)
                except Exception as e:
                    _logger.warning(f"Failed to send confirmation email: {str(e)}")
                
                return {
                    'status': 'success',
                    'redirect': '/my_subscription',
                    'message': 'Subscription activated successfully!'
                }
            
            elif subscription.status == 'incomplete':
                if invoice and hasattr(invoice, 'payment_intent'):
                    payment_intent = invoice.payment_intent
                    
                    if payment_intent and payment_intent.status == 'requires_action':
                        return {
                            'status': 'requires_action',
                            'client_secret': payment_intent.client_secret,
                            'subscription_id': subscription.id,
                            'payment_intent_id': payment_intent.id
                        }
                
                return {
                    'status': 'error',
                    'message': 'Payment incomplete. Please try again.'
                }
            
            else:
                return {
                    'status': 'error',
                    'message': f'Subscription status: {subscription.status}. Please try again.'
                }
            
        except stripe.error.CardError as e:
            _logger.error(f"Stripe CardError: {str(e)}")
            return {
                'status': 'error',
                'message': f'Card declined: {e.user_message}'
            }
        except stripe.error.StripeError as e:
            _logger.error(f"Stripe Error: {str(e)}")
            return {
                'status': 'error',
                'message': f'Payment failed: {str(e)}'
            }
        except Exception as e:
            _logger.error(f"Subscription creation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': f'Error: {str(e)}'
            }
    
    @http.route('/subscription/reactivate', type='http', auth='user', website=True)
    def subscription_reactivate(self, **kw):
        """Reactivate cancelled subscription"""
        user = request.env.user
        partner = user.partner_id
        
        cancelled_sub = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'cancelled')
        ], limit=1)
        
        if not cancelled_sub:
            return request.redirect('/my_subscription')
        
        try:
            stripe_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'stripe'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if stripe_provider and cancelled_sub.stripe_subscription_id:
                stripe.api_key = stripe_provider.stripe_secret_key
                
                ICP = request.env['ir.config_parameter'].sudo()
                stripe_price_key = f'stripe_{cancelled_sub.subscription_type}_price_id'
                STRIPE_PRICE_ID = ICP.get_param(stripe_price_key)
                
                try:
                    stripe_sub = stripe.Subscription.retrieve(cancelled_sub.stripe_subscription_id)
                    
                    if stripe_sub.status == 'canceled':
                        new_subscription = stripe.Subscription.create(
                            customer=cancelled_sub.stripe_customer_id,
                            items=[{'price': STRIPE_PRICE_ID}],
                            metadata={
                                'subscription_type': cancelled_sub.subscription_type,
                                'partner_id': partner.id,
                            }
                        )
                        
                        cancelled_sub.sudo().write({
                            'status': 'active',
                            'stripe_subscription_id': new_subscription.id,
                            'cancelled_date': False,
                        })
                    else:
                        cancelled_sub.sudo().write({
                            'status': 'active',
                            'cancelled_date': False,
                        })
                except stripe.error.InvalidRequestError:
                    cancelled_sub.sudo().write({
                        'status': 'active',
                        'cancelled_date': False,
                    })
            else:
                cancelled_sub.sudo().write({
                    'status': 'active',
                    'cancelled_date': False,
                })
            
            self._send_reactivation_email(cancelled_sub)
            
            return request.redirect('/my_subscription?reactivated=1')
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return request.render('us_arena_website.error_template', {
                'error': f'Failed to reactivate subscription: {str(e)}'
            })
    
    @http.route('/subscription/cancel', type='json', auth='user', csrf=False)
    def cancel_subscription(self, **kw):
        """Cancel user subscription"""
        user = request.env.user
        partner = user.partner_id
        
        subscription = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'active')
        ], limit=1)
        
        if not subscription:
            return {'status': 'error', 'message': 'No active subscription found'}
        
        try:
            stripe_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'stripe'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if stripe_provider:
                stripe.api_key = stripe_provider.stripe_secret_key
                
                if subscription.stripe_subscription_id:
                    try:
                        stripe.Subscription.delete(subscription.stripe_subscription_id)
                    except:
                        pass
            
            subscription.action_cancel_subscription()
            self._send_cancellation_email(subscription)
            
            return {
                'status': 'success',
                'message': 'Subscription cancelled successfully',
                'redirect': '/my_subscription'
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
        
    @http.route('/debug/get_stripe_details', type='http', auth='user', website=True)
    def get_stripe_details(self, **kw):

        provider = request.env['payment.provider'].sudo().search([('code', '=', 'stripe')], limit=1)
        stripe.api_key = provider.stripe_secret_key

        param_keys = [
            'stripe_subscription_a_product_id',
            'stripe_subscription_b_product_id',
            'stripe_subscription_c_product_id',
        ]

        result_html = "<h3>Stripe Product + Price Details</h3><br>"

        for param in param_keys:
            product_id = request.env['ir.config_parameter'].sudo().get_param(param)

            if not product_id:
                result_html += f"<p><b>{param}</b>: ❌ Missing Product ID</p><hr>"
                continue

            try:
                product = stripe.Product.retrieve(product_id)
                prices = stripe.Price.list(product=product_id, active=True)

                if prices.data:
                    price_obj = prices.data[0]
                    price_amount = price_obj["unit_amount"] / 100.0
                    currency = price_obj["currency"].upper()
                    interval = price_obj["recurring"]["interval"] if price_obj.get("recurring") else "one-time"
                else:
                    price_amount = "N/A"
                    currency = "-"
                    interval = "-"

                result_html += (
                    f"<p><b>{product.get('name')}</b><br>"
                    f"Product ID: {product_id}<br>"
                    f"Price: {price_amount} {currency}<br>"
                )

            except Exception as e:
                result_html += f"<p><b>{param}</b>: ❌ Stripe Error → {str(e)}</p><hr>"

        return result_html

    @http.route('/subscription/upgrade', type='http', auth='user', website=True)
    def subscription_upgrade(self, new_subscription_type, **kw):
        """Upgrade subscription to a higher-tier plan (prevents downgrades)"""
        import stripe
        
        user = request.env.user
        partner = user.partner_id
        
        # Define subscription hierarchy (lower number = lower tier)
        SUBSCRIPTION_HIERARCHY = {
            'subscription_a': 1,
            'subscription_b': 2,
            'subscription_c': 3,
        }
        
        valid_types = ['subscription_a', 'subscription_b', 'subscription_c']
        if new_subscription_type not in valid_types:
            return request.redirect('/subscription/plans')
        
        # Get current active subscriptions to find same-group conflict
        today = fields.Date.today()
        active_subs = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'active'),
        ])
        active_subs = active_subs.filtered(
            lambda s: s.end_date and s.end_date >= today
        )

        # Look up group for target type via admin type config
        type_config = request.env['subscription.type.config'].sudo()
        requested_group_id = type_config.get_group_for_type(new_subscription_type)

        # Find the current subscription in the same group (if any)
        current_subscription = None
        for sub in active_subs:
            if sub.subscription_type == new_subscription_type:
                return request.redirect('/my_subscription?error=same_plan')
            sub_group_id = type_config.get_group_for_type(sub.subscription_type)
            if requested_group_id and sub_group_id == requested_group_id:
                current_subscription = sub
                break

        if not current_subscription:
            # No same-group conflict — redirect to normal checkout (handles cross-group)
            return request.redirect(f'/subscription/checkout?subscription_type={new_subscription_type}')

        # If we reach here, it's a valid upgrade
        
        # Get Stripe provider
        stripe_provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'stripe'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        if not stripe_provider:
            return request.render('website.404', {
                'status_code': 500,
                'status_message': 'Stripe payment is not enabled. Please contact administrator.'
            })
        
        # Get system parameters
        ICP = request.env['ir.config_parameter'].sudo()
        
        # Map subscription type to product parameter key
        product_param_map = {
            'subscription_a': 'stripe_subscription_a_product_id',
            'subscription_b': 'stripe_subscription_b_product_id',
            'subscription_c': 'stripe_subscription_c_product_id',
        }
        
        new_product_id = ICP.get_param(product_param_map[new_subscription_type])
        
        if not new_product_id:
            return request.render('website.404', {
                'status_code': 500,
                'status_message': f'Stripe product ID for {new_subscription_type} is not configured.'
            })
        
        # Subscription names
        subscription_names = {
            'subscription_a': 'Membership A',
            'subscription_b': 'Membership B',
            'subscription_c': 'Membership C',
        }
        
        # Default values
        new_price = 20.00
        new_price_id = None
        currency = 'USD'
        
        # Fetch the highest price for the new subscription
        try:
            stripe.api_key = stripe_provider.stripe_secret_key
            
            prices_list = stripe.Price.list(
                product=new_product_id,
                active=True,
                limit=100
            )
            
            if prices_list.data:
                monthly_prices = [
                    p for p in prices_list.data 
                    if p.recurring and p.recurring.interval == 'month' and p.unit_amount
                ]
                
                if monthly_prices:
                    highest_price = max(monthly_prices, key=lambda p: p.unit_amount)
                    new_price = highest_price.unit_amount / 100
                    new_price_id = highest_price.id
                    currency = highest_price.currency.upper()
                else:
                    return request.render('website.404', {
                        'status_code': 500,
                        'status_message': 'No valid pricing found for the new subscription.'
                    })
            else:
                return request.render('website.404', {
                    'status_code': 500,
                    'status_message': 'No pricing found for the new subscription.'
                })
        except Exception as e:
            _logger.error(f"Failed to fetch prices for upgrade: {str(e)}")
            return request.render('website.404', {
                'status_code': 500,
                'status_message': 'Failed to load subscription pricing.'
            })
        
        # Get discount info for new subscription
        discount_config = request.env['subscription.discount.config'].sudo().get_active_config()
        lane_discount = 0
        merch_discount = 0
        
        if discount_config:
            discounts = discount_config.get_discounts_for_subscription(new_subscription_type)
            lane_discount = discounts.get('lane_rental_discount', 0)
            merch_discount = discounts.get('merchandise_discount', 0)
        
        values = {
            'user': user,
            'partner': partner,
            'current_subscription': current_subscription,
            'current_subscription_name': subscription_names.get(current_subscription.subscription_type, 'Current Plan'),
            'new_subscription_type': new_subscription_type,
            'new_subscription_name': subscription_names.get(new_subscription_type, 'New Plan'),
            'new_price': new_price,
            'currency': currency,
            'new_price_id': new_price_id,
            'lane_discount': lane_discount,
            'merch_discount': merch_discount,
            'stripe_publishable_key': stripe_provider.stripe_publishable_key,
            'is_test_mode': stripe_provider.state == 'test',
        }
        
        return request.render('us_arena_website.subscription_upgrade_template', values)

    @http.route('/subscription/process_upgrade', type='json', auth='user', csrf=False)
    def process_subscription_upgrade(self, new_subscription_type, new_price_id, payment_method_id, **kw):
        """Process the subscription upgrade/change"""
        from datetime import timedelta
        import stripe
        
        user = request.env.user
        partner = user.partner_id
        
        valid_types = ['subscription_a', 'subscription_b', 'subscription_c']
        if new_subscription_type not in valid_types:
            return {
                'status': 'error',
                'message': 'Invalid subscription type'
            }
        
        # Get current active subscription
        current_subscription = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'active')
        ], limit=1)
        
        if not current_subscription:
            return {
                'status': 'error',
                'message': 'No active subscription found'
            }
        
        # Check if trying to "upgrade" to the same plan
        if current_subscription.subscription_type == new_subscription_type:
            return {
                'status': 'error',
                'message': 'You are already subscribed to this plan'
            }
        
        try:
            stripe_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'stripe'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not stripe_provider:
                return {
                    'status': 'error',
                    'message': 'Stripe is not configured'
                }
            
            stripe.api_key = stripe_provider.stripe_secret_key
            
            # Get or verify Stripe customer
            stripe_customer_id = current_subscription.stripe_customer_id
            
            if not stripe_customer_id:
                return {
                    'status': 'error',
                    'message': 'Stripe customer ID not found'
                }
            
            # Attach new payment method to customer
            try:
                stripe.PaymentMethod.attach(
                    payment_method_id,
                    customer=stripe_customer_id,
                )
                
                # Set as default payment method
                stripe.Customer.modify(
                    stripe_customer_id,
                    invoice_settings={
                        'default_payment_method': payment_method_id,
                    },
                )
                _logger.info(f"Payment method {payment_method_id} attached to customer {stripe_customer_id}")
            except Exception as e:
                _logger.error(f"Failed to attach payment method: {str(e)}")
                return {
                    'status': 'error',
                    'message': 'Failed to attach payment method'
                }
            
            # Step 1: Cancel old Stripe subscription
            if current_subscription.stripe_subscription_id:
                try:
                    stripe.Subscription.delete(current_subscription.stripe_subscription_id)
                    _logger.info(f"Cancelled old Stripe subscription: {current_subscription.stripe_subscription_id}")
                except Exception as e:
                    _logger.warning(f"Failed to cancel old Stripe subscription: {str(e)}")
            
            # Step 2: Create new Stripe subscription with new payment method
            new_subscription = stripe.Subscription.create(
                customer=stripe_customer_id,
                items=[{
                    'price': new_price_id,
                }],
                default_payment_method=payment_method_id,
                payment_settings={
                    'payment_method_types': ['card'],
                    'save_default_payment_method': 'on_subscription',
                },
                expand=['latest_invoice.payment_intent'],
                metadata={
                    'subscription_type': new_subscription_type,
                    'partner_id': partner.id,
                    'upgraded_from': current_subscription.subscription_type,
                }
            )
            
            _logger.info(f"Created new Stripe subscription: {new_subscription.id}")
            
            invoice = new_subscription.latest_invoice
            
            if new_subscription.status == 'active':
                today = fields.Date.today()
                
                # Get discount configuration for new subscription
                config = request.env['subscription.discount.config'].sudo().get_active_config()
                lane_discount = 0
                merch_discount = 0
                
                if config:
                    discounts = config.get_discounts_for_subscription(new_subscription_type)
                    lane_discount = discounts.get('lane_rental_discount', 0)
                    merch_discount = discounts.get('merchandise_discount', 0)
                
                # Get the actual price from Stripe
                try:
                    stripe_price_obj = stripe.Price.retrieve(new_price_id)
                    subscription_price = stripe_price_obj.unit_amount / 100 if stripe_price_obj.unit_amount else 20.00
                except Exception as e:
                    _logger.warning(f"Failed to retrieve price: {str(e)}")
                    subscription_price = 20.00
                
                # Step 3: Cancel old local subscription
                current_subscription.sudo().write({
                    'status': 'cancelled',
                    'cancelled_date': today,
                })
                
                # Step 4: Create new local subscription record
                new_subscription_record = request.env['user.subscription'].sudo().create({
                    'user_id': user.id,
                    'partner_id': partner.id,
                    'subscription_type': new_subscription_type,
                    'price': subscription_price,
                    'status': 'active',
                    'start_date': today,
                    'end_date': today + timedelta(days=31),
                    'next_billing_date': today + timedelta(days=31),
                    'stripe_subscription_id': new_subscription.id,
                    'stripe_customer_id': stripe_customer_id,
                    'stripe_price_id': new_price_id,
                    'gym_access': True,
                    'lane_rental_discount': lane_discount,
                    'merchandise_discount': merch_discount,
                })
                
                _logger.info(f"Created new local subscription: {new_subscription_record.id}")
                
                # Send upgrade confirmation email
                try:
                    self._send_upgrade_confirmation_email(new_subscription_record, current_subscription)
                except Exception as e:
                    _logger.warning(f"Failed to send upgrade email: {str(e)}")
                
                return {
                    'status': 'success',
                    'redirect': '/my_subscription?upgraded=1',
                    'message': 'Subscription upgraded successfully!'
                }
            
            elif new_subscription.status == 'incomplete':
                if invoice and hasattr(invoice, 'payment_intent'):
                    payment_intent = invoice.payment_intent
                    
                    if payment_intent and payment_intent.status == 'requires_action':
                        return {
                            'status': 'requires_action',
                            'client_secret': payment_intent.client_secret,
                            'subscription_id': new_subscription.id,
                        }
                
                return {
                    'status': 'error',
                    'message': 'Payment incomplete. Please try again.'
                }
            
            else:
                return {
                    'status': 'error',
                    'message': f'Subscription status: {new_subscription.status}. Please try again.'
                }
            
        except stripe.error.CardError as e:
            _logger.error(f"Stripe CardError during upgrade: {str(e)}")
            return {
                'status': 'error',
                'message': f'Card declined: {e.user_message}'
            }
        except stripe.error.StripeError as e:
            _logger.error(f"Stripe Error during upgrade: {str(e)}")
            return {
                'status': 'error',
                'message': f'Payment failed: {str(e)}'
            }
        except Exception as e:
            _logger.error(f"Upgrade error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': f'Error: {str(e)}'
            }

    
    def _send_subscription_confirmation_email(self, subscription):
        """Send subscription confirmation email"""
        username = subscription.partner_id.name
        
        email_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #0a2351; color: white; padding: 20px; text-align: center;">
                    <h1>Welcome to United Sports Arena!</h1>
                </div>
                <div style="padding: 30px; background: #f9f9f9;">
                    <p>Dear {username},</p>
                    <p>Your subscription has been activated successfully! 🎉</p>
                    <p style="text-align: center; margin-top: 30px;">
                        <a href="{request.httprequest.host_url}my/subscription" 
                           style="background: #0a2351; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Manage Subscription
                        </a>
                    </p>
                    <p style="margin-top: 30px;">Thank you for choosing United Sports Arena!</p>
                    <p>Best regards,<br><strong>United Sports Arena Team</strong></p>
                </div>
            </div>
        """
        
        mail_server = request.env['ir.mail_server'].sudo().search([
            ('name', '=', 'USArena - Invoice')
        ], limit=1)
        
        email_from = f'United Sports Arena <{mail_server.smtp_user}>' if mail_server else 'noreply@unitedsportsarena.com'
        
        mail_values = {
            'subject': 'Subscription Activated - United Sports Arena',
            'body_html': email_body,
            'email_from': email_from,
            'email_to': subscription.partner_id.email,
        }
        
        mail = request.env['mail.mail'].sudo().create(mail_values)
        mail.send()
    
    def _send_reactivation_email(self, subscription):
        """Send subscription reactivation email"""
        username = subscription.partner_id.name
        
        email_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #0a2351; color: white; padding: 20px; text-align: center;">
                    <h1>Welcome Back to United Sports Arena!</h1>
                </div>
                <div style="padding: 30px; background: #f9f9f9;">
                    <p>Dear {username},</p>
                    <p>Your subscription has been reactivated successfully! 🎉</p>
                    <p style="text-align: center; margin-top: 30px;">
                        <a href="{request.httprequest.host_url}my/subscription" 
                           style="background: #0a2351; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Manage Subscription
                        </a>
                    </p>
                    <p style="margin-top: 30px;">We're glad to have you back!</p>
                    <p>Best regards,<br><strong>United Sports Arena Team</strong></p>
                </div>
            </div>
        """
        
        mail_server = request.env['ir.mail_server'].sudo().search([
            ('name', '=', 'USArena - Invoice')
        ], limit=1)
        
        email_from = f'United Sports Arena <{mail_server.smtp_user}>' if mail_server else 'noreply@unitedsportsarena.com'
        
        mail_values = {
            'subject': 'Subscription Reactivated - United Sports Arena',
            'body_html': email_body,
            'email_from': email_from,
            'email_to': subscription.partner_id.email,
        }
        
        mail = request.env['mail.mail'].sudo().create(mail_values)
        mail.send()
    
    def _send_cancellation_email(self, subscription):
        """Send subscription cancellation email"""
        username = subscription.partner_id.name
        
        email_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="padding: 30px; background: #f9f9f9;">
                    <p>Dear {username},</p>
                    <p>Your subscription has been cancelled as requested.</p>
                    <p>We're sorry to see you go! If you'd like to reactivate your subscription, you can do so anytime from your account.</p>
                    <p>Best regards,<br><strong>United Sports Arena Team</strong></p>
                </div>
            </div>
        """
        
        mail_server = request.env['ir.mail_server'].sudo().search([
            ('name', '=', 'USArena - Invoice')
        ], limit=1)
        
        mail_values = {
            'subject': 'Subscription Cancelled - United Sports Arena',
            'body_html': email_body,
            'email_from': mail_server.smtp_user if mail_server else 'noreply@unitedsportsarena.com',
            'email_to': subscription.partner_id.email,
        }
        
        mail = request.env['mail.mail'].sudo().create(mail_values)
        mail.send()



class SubscriptionController(http.Controller):
    @http.route('/my_subscription', type='http', auth='user', website=True)
    def my_subscription(self, **kw):
        user = request.env.user
        partner = user.partner_id

        # Get ALL subscriptions (for legacy display / cancelled status)
        subscription = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id)
        ], order='create_date desc', limit=1)

        if not subscription:
            subscription = request.env['user.subscription'].sudo().search([
                ('user_id', '=', user.id)
            ], order='create_date desc', limit=1)

        # Get ALL currently active subscriptions (multi-group support)
        today = fields.Date.today()
        all_active_subs = request.env['user.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('status', '=', 'active'),
        ])
        all_active_subs = all_active_subs.filtered(
            lambda s: s.end_date and s.end_date >= today
        )

        # Stripe setup
        provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'stripe')
        ], limit=1)
        stripe.api_key = provider.stripe_secret_key

        discount_config = request.env['subscription.discount.config'].sudo().get_active_config()

        active_subscriptions = []
        for sub in all_active_subs:
            product_id_param = f"stripe_{sub.subscription_type}_product_id"
            product_id = request.env['ir.config_parameter'].sudo().get_param(product_id_param)

            product_name = sub.subscription_type_display
            product_price = sub.price
            price_currency = "USD"
            interval = "month"

            if product_id:
                try:
                    stripe_product = stripe.Product.retrieve(product_id)
                    product_name = stripe_product.get('name', product_name)
                    prices = stripe.Price.list(product=product_id, active=True)
                    if prices.data:
                        price_obj = prices.data[0]
                        product_price = price_obj["unit_amount"] / 100.0
                        price_currency = price_obj["currency"].upper()
                        interval = price_obj.get('recurring', {}).get('interval', 'month')
                except Exception:
                    pass

            # Discounts
            lane_discount = 0
            merch_discount = 0
            if discount_config:
                discounts = discount_config.get_discounts_for_subscription(sub.subscription_type)
                lane_discount = discounts.get('lane_rental_discount', 0)
                merch_discount = discounts.get('merchandise_discount', 0)
            else:
                fallback = {
                    'subscription_a': (5, 5),
                    'subscription_b': (10, 10),
                    'subscription_c': (15, 20),
                }
                lane_discount, merch_discount = fallback.get(sub.subscription_type, (0, 0))

            benefit_lines = []
            if lane_discount > 0:
                benefit_lines.append({'discount': lane_discount, 'label': 'Lane Rental'})
            if merch_discount > 0:
                benefit_lines.append({'discount': merch_discount, 'label': 'Merchandise'})

            active_subscriptions.append({
                'id': sub.id,
                'subscription': sub,
                'subscription_type': sub.subscription_type,
                'subscription_name': product_name,
                'group_name': sub.group_id.name if sub.group_id else None,
                'price': product_price,
                'currency': price_currency,
                'interval': interval,
                'start_date': sub.start_date,
                'next_billing_date': sub.next_billing_date,
                'status': sub.status,
                'lane_discount': lane_discount,
                'merch_discount': merch_discount,
                'benefit_lines': benefit_lines,
            })

        # Legacy single-sub details (for the cancelled / non-active display)
        subscription_details = active_subscriptions[0] if active_subscriptions else None

        return request.render('us_arena_website.my_subscription_template', {
            'subscription': subscription,
            'subscription_details': subscription_details,
            'active_subscriptions': active_subscriptions,
            'user': user,
            'partner': partner,
            'page_name': 'subscription',
        })




class PaymentController(http.Controller):

    def _finalize_booking(self, order):
        """
        Ensure order + slots are finalized after payment
        """
        if not order:
            return

        if order.state != 'sale':
            order.action_confirm()

        # Lock selected slots
        for slot in order.selected_slots:
            slot.sudo().write({
                'state': 'booked',
                'order_id': order.id,
            })

    @http.route('/payment/status', type='http', auth='public', website=True, csrf=False)
    def payment_status(self, **kw):
        """
        Handle payment status page
        """
        order = request.website.sale_get_order()

        if order and order.state == 'draft':
            # Check if payment was successful
            tx = request.env['payment.transaction'].sudo().search([
                ('sale_order_ids', 'in', order.ids),
                ('state', '=', 'done')
            ], limit=1)

            if tx:
                self._finalize_booking(order)

        return request.render('website_sale.payment_confirmation', {
            'order': order
        })
        
        
        
class StripeWebhookController(http.Controller):

    @http.route('/stripe/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def stripe_webhook(self, **kwargs):
        """
        Handle incoming Stripe webhook events.
        Must be registered in Stripe Dashboard → Developers → Webhooks.
        """
        payload = request.httprequest.data
        sig_header = request.httprequest.headers.get('Stripe-Signature')

        # Get your webhook secret from Odoo system parameters
        # Set it via: Settings → Technical → System Parameters → stripe_webhook_secret
        webhook_secret = request.env['ir.config_parameter'].sudo().get_param(
            'stripe_webhook_secret'
        )

        # Verify the request is genuinely from Stripe
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError:
            return request.make_response('Invalid signature', status=400)
        except Exception as e:
            return request.make_response(f'Error: {str(e)}', status=400)

        event_type = event['type']
        data = event['data']['object']

        # ─── Auto-renewal: invoice paid successfully ───────────────────────
        if event_type == 'invoice.payment_succeeded':
            stripe_subscription_id = data.get('subscription')
            if not stripe_subscription_id:
                return request.make_response('OK', status=200)

            # Only process renewal invoices, not the first payment
            billing_reason = data.get('billing_reason')
            if billing_reason not in ('subscription_cycle', 'subscription_update'):
                return request.make_response('OK', status=200)

            subscription = request.env['user.subscription'].sudo().search([
                ('stripe_subscription_id', '=', stripe_subscription_id)
            ], limit=1)

            if subscription:
                # Retrieve the latest subscription data from Stripe
                provider = request.env['payment.provider'].sudo().search([
                    ('code', '=', 'stripe')
                ], limit=1)
                stripe.api_key = provider.stripe_secret_key

                stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
                # Stripe gives Unix timestamps — convert to date
                new_end_date = datetime.utcfromtimestamp(
                    stripe_sub['current_period_end']
                ).date()
                new_billing_date = new_end_date

                subscription.write({
                    'end_date': new_end_date,
                    'next_billing_date': new_billing_date,
                    'status': 'active',
                })

        # ─── Subscription status changed (cancelled, paused, etc.) ─────────
        elif event_type == 'customer.subscription.updated':
            stripe_subscription_id = data.get('id')
            stripe_status = data.get('status')  # active, canceled, past_due, etc.

            subscription = request.env['user.subscription'].sudo().search([
                ('stripe_subscription_id', '=', stripe_subscription_id)
            ], limit=1)

            if subscription:
                # Map Stripe status → your Odoo status
                status_map = {
                    'active': 'active',
                    'canceled': 'cancelled',
                    'past_due': 'pending',
                    'unpaid': 'pending',
                    'incomplete_expired': 'expired',
                }
                odoo_status = status_map.get(stripe_status)

                # Always sync the period end date
                new_end_date = datetime.utcfromtimestamp(
                    data['current_period_end']
                ).date()

                write_vals = {
                    'end_date': new_end_date,
                    'next_billing_date': new_end_date,
                }
                if odoo_status:
                    write_vals['status'] = odoo_status
                if odoo_status == 'cancelled':
                    write_vals['cancelled_date'] = fields.Date.today()

                subscription.write(write_vals)

        # ─── Payment failed ─────────────────────────────────────────────────
        elif event_type == 'invoice.payment_failed':
            stripe_subscription_id = data.get('subscription')
            if stripe_subscription_id:
                subscription = request.env['user.subscription'].sudo().search([
                    ('stripe_subscription_id', '=', stripe_subscription_id)
                ], limit=1)
                if subscription:
                    subscription.write({'status': 'pending'})

        return request.make_response('OK', status=200)
