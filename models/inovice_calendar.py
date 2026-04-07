from odoo import models, fields, api
import json
from datetime import datetime, timedelta

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def _create_invoices(self, grouped=False, final=False, date=None):
        # Call the original method to create invoices
        invoices = super(SaleOrder, self)._create_invoices(grouped=grouped, final=final, date=date)
        
        # Your custom action here
       # for invoice in invoices:
            # Perform your custom action for each created invoice
      #      self._perform_custom_action(invoice)
            
        return invoices
    
    def _perform_custom_action(self, invoice):
        selected_sales_order = self.env['sale.order'].sudo().search([('name', '=', invoice.invoice_origin)])
        slots = self.env['product.slot'].sudo().search([
            ('sale_id', '=', selected_sales_order.id)
        ])
        for slot in slots:
            slot.write({'is_booked': True})
        selected_product_slot = self.env['product.slot'].sudo().search([('sale_id', '=', selected_sales_order.id)], limit=1)
        product_id = selected_product_slot.product_id
        product_details = self.env['product.product'].sudo().search([('id', '=', product_id.id)])
        product_tmpl_id = product_details.product_tmpl_id
        product_temp_details = self.env['product.template'].sudo().search([('id', '=', product_tmpl_id.id)])
        selected_slots = selected_sales_order.selected_slots
        CalendarEvent = self.env['calendar.event'].sudo()
        slots_to_process = json.loads(selected_slots)
        partner_id = selected_sales_order.partner_id
        dayname = selected_product_slot.dayname        
        rental_start_date = selected_sales_order.rental_start_date
        rental_end_date = selected_sales_order.rental_return_date
        difference = (rental_end_date - rental_start_date).days
       
        if difference == 1:
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

                
                event_start = datetime.combine(selected_date_obj.date(), start_time)+ timedelta(hours=4)
                event_end = datetime.combine(selected_date_obj.date(), end_time)+ timedelta(hours=4)

                if event_end < event_start:
                    event_end = event_end + timedelta(days=1)

                event = CalendarEvent.with_context(tz='America/New_York').create({
                    'name': f"{product_temp_details.name}: {partner_id.name} | {slot['lane_name']} Starts at {event_start}",
                    'start': event_start,
                    'stop': event_end,
                    'partner_ids': [(4, partner_id.id)],
                    'allday': False,
                    'sales_order_id': selected_sales_order.id
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
                            'sales_order_id': selected_sales_order.id
                        })
                rental_start_date += timedelta(days=1)
            
    #    extra_addons = self.env['extra.addons'].sudo().search([
   #         ('sale_id', '=', selected_sales_order.id)
    #    ])
   #     for addons in extra_addons:
   #         addons.is_book = True
        return['1']
