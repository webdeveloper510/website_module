# -*- coding: utf-8 -*-
{
    'name': "US Arena Cricket Management",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'website_sale','website','sale_management','crm','stock','accountant','purchase','point_of_sale','hr','contacts','hr_payroll','sale_renting'],

    # always loaded
    'data': [
        'views/arena_menu.xml',
        'security/ir.model.access.csv',
        'views/website.xml',
        'views/home_template.xml',
        'views/about_us.xml',
        'views/teams.xml',
        'views/lane_rental.xml',
        'views/shop_page.xml',
        'views/league.xml',
        'views/coaching.xml',
        'views/sigin_signup.xml',
        'views/product_template.xml',
        'views/add_cart_template.xml',
        'views/lane_cart.xml',
        'views/member_subscription.xml',
        'views/subscription_template.xml',
        'views/our_team.xml',
        'views/box_event.xml',
        'views/checkout_page.xml',
        'views/my_subscription.xml',
        'views/portal_templates.xml',
        'views/subscription_views.xml',
        'views/subscription_discount_config_views.xml',
        'views/payment_discount_fix.xml',
        'views/upgrade_templates.xml',
        'views/payment_status_template.xml',
        'views/cron.xml',
    ],
'assets': {
        'web.assets_frontend': [
            'us_arena_website/static/src/js/lane.js',
        ],
    },

}
