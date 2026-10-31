"""Run after migrations: python seed_demo.py [--with-demo-admin]."""
import argparse
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.conf import settings
from django.db import transaction
from restaurant.models import User, UserProfile, Cart, MenuCategory, MenuItem, Table, RestaurantInfo, Review


@transaction.atomic
def seed(with_admin=False):
    categories = [
        ('salads', 'Салаты', [('greek-salad', 'Греческий салат', '350.00', True), ('caesar', 'Цезарь с курицей', '420.00', False), ('warm-salad', 'Тёплый овощной салат', '390.00', True)]),
        ('main', 'Горячие блюда', [('steak', 'Стейк с картофелем', '1200.00', False), ('salmon', 'Лосось с овощами', '950.00', False), ('risotto', 'Ризотто с грибами', '520.00', True), ('chicken', 'Курица на гриле', '590.00', False)]),
        ('soups', 'Супы', [('pumpkin-soup', 'Тыквенный суп', '280.00', True), ('chicken-soup', 'Куриный суп', '300.00', False)]),
        ('desserts', 'Десерты', [('cheesecake', 'Чизкейк', '320.00', True), ('brownie', 'Брауни', '290.00', True), ('ice-cream', 'Мороженое', '200.00', True)]),
        ('drinks', 'Напитки', [('coffee', 'Капучино', '180.00', True), ('tea', 'Чай', '120.00', True), ('lemonade', 'Домашний лимонад', '220.00', True)]),
    ]
    for position, (slug, name, dishes) in enumerate(categories):
        category, _ = MenuCategory.objects.get_or_create(slug=slug, defaults={'name': name, 'order': position})
        for index, (dish_slug, dish_name, price, vegetarian) in enumerate(dishes):
            MenuItem.objects.get_or_create(slug=dish_slug, defaults={
                'category': category, 'name': dish_name, 'price': price,
                'description': f'{dish_name}. Демонстрационная позиция меню.',
                'is_vegetarian': vegetarian, 'is_popular': index == 0,
            })
    for number, seats in enumerate([2, 2, 4, 4, 6, 8], 1):
        Table.objects.get_or_create(number=number, defaults={'seats': seats})
    RestaurantInfo.objects.get_or_create(pk=1, defaults={
        'name': 'MAISON Restaurant', 'address': 'Бишкек — демонстрационный адрес',
        'email': 'hello@example.com', 'phone': '+996700000000',
        'about': 'Демонстрационный ресторан MAISON. Замените контакты и описание в админке.',
    })
    if with_admin:
        if not settings.DEBUG:
            raise RuntimeError('Демонстрационный администратор доступен только при DEBUG=True.')
        user, created = User.objects.get_or_create(username='demo_admin', defaults={
            'email': 'demo-admin@example.com', 'is_staff': True, 'is_superuser': True,
        })
        if created:
            user.set_password('MaisonDemo!2026')
            user.save()
            UserProfile.objects.create(user=user, phone='+996700000001')
            Cart.objects.create(user=user)
        Review.objects.get_or_create(user=user, text='Демонстрационный отзыв: понравилась кухня и обслуживание.', defaults={'rating': 5, 'is_approved': True})
        print('Локальный демо-вход (если создан впервые): demo_admin / MaisonDemo!2026')
    print('Готово: 5 категорий, 15 блюд, 6 столов. Повторный запуск не дублирует данные.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-demo-admin', action='store_true')
    seed(parser.parse_args().with_demo_admin)
