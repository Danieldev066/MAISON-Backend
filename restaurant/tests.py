from datetime import timedelta, time
from decimal import Decimal
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from .models import User, UserProfile, MenuCategory, MenuItem, Table, Reservation, Order, Review, CartItem, RestaurantInfo, ContactMessage

PREFIX = '/api/v1/'


class RestaurantAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('client', email='client@example.com', password='GoodPass!234')
        cls.other = User.objects.create_user('other', email='other@example.com', password='OtherPass!234')
        cls.admin = User.objects.create_superuser('admin', email='admin@example.com', password='AdminPass!234')
        UserProfile.objects.create(user=cls.user, phone='+996700123456')
        cls.category = MenuCategory.objects.create(name='Супы', slug='soups')
        cls.dish = MenuItem.objects.create(category=cls.category, name='Суп', slug='soup', price='250.00', is_popular=True)
        cls.table = Table.objects.create(number=1, seats=4)
        RestaurantInfo.objects.create()
        cls.day = timezone.localdate() + timedelta(days=2)

    def setUp(self):
        cache.clear()

    def login(self, user=None):
        self.client.force_authenticate(user or self.user)

    def booking(self, **changes):
        data = {'table': self.table.pk, 'name': 'Гость', 'phone': '+996555123456', 'date': str(self.day), 'time': '14:00', 'guests_count': 2}
        data.update(changes)
        return self.client.post(PREFIX + 'reservations/', data)

    def add_dish(self, quantity=2):
        return self.client.post(PREFIX + 'cart/items/', {'item': self.dish.pk, 'quantity': quantity})

    def checkout(self, **changes):
        data = {'order_type': 'pickup', 'phone': '+996700123456'}
        data.update(changes)
        return self.client.post(PREFIX + 'orders/', data)

    def test_register_login_refresh(self):
        response = self.client.post(PREFIX + 'auth/register/', {'username': 'new', 'email': 'NEW@example.com', 'phone': '+996777123456', 'password': 'NewSecret!234'})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('password', response.data)
        self.assertEqual(response.data['email'], 'new@example.com')
        tokens = self.client.post(PREFIX + 'auth/login/', {'username': 'new', 'password': 'NewSecret!234'})
        self.assertEqual(tokens.status_code, 200)
        self.assertEqual(self.client.post(PREFIX + 'auth/token/refresh/', {'refresh': tokens.data['refresh']}).status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens.data['access'])
        self.assertEqual(self.client.get(PREFIX + 'profile/').data['username'], 'new')

    def test_registration_rejects_duplicate_email_case(self):
        response = self.client.post(PREFIX + 'auth/register/', {'username': 'new', 'email': 'CLIENT@example.com', 'phone': '+996777123456', 'password': 'NewSecret!234'})
        self.assertEqual(response.status_code, 400)

    def test_registration_rejects_duplicate_phone_and_weak_password(self):
        data = {'username': 'new', 'email': 'new@example.com', 'phone': '+996700123456', 'password': '123'}
        response = self.client.post(PREFIX + 'auth/register/', data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.data)
        self.assertIn('password', response.data)

    def test_profile_cannot_grant_staff(self):
        self.login()
        result = self.client.patch(PREFIX + 'profile/', {'first_name': 'Даниел', 'is_staff': True})
        self.assertEqual(result.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.user.first_name, 'Даниел')

    def test_profile_duplicate_email_and_phone(self):
        UserProfile.objects.create(user=self.other, phone='+996555555555')
        self.login()
        response = self.client.patch(PREFIX + 'profile/', {'email': 'OTHER@example.com', 'phone': '+996555555555'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)
        self.assertIn('phone', response.data)

    def test_menu_search_filter_and_pagination(self):
        result = self.client.get(PREFIX + 'menu/?search=Суп&ordering=-price&category=' + str(self.category.pk))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(result.data['results'][0]['price'], '250.00')
        self.assertEqual(self.client.get(PREFIX + 'menu/soup/').status_code, 200)
        self.assertEqual(self.client.get(PREFIX + 'menu/popular/').data['count'], 1)
        self.category.is_active = False
        self.category.save()
        self.assertEqual(self.client.get(PREFIX + 'menu/').data['count'], 0)

    def test_guest_booking(self):
        response = self.booking(status='confirmed')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(Reservation.objects.get().user)
        self.assertEqual(response.data['status'], 'pending')

    def test_overlapping_reservations(self):
        self.assertEqual(self.booking().status_code, 201)
        for booking_time in ['12:01', '13:00', '14:00', '15:59']:
            self.assertEqual(self.booking(time=booking_time).status_code, 400)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_adjacent_bookings_allowed(self):
        self.booking()
        self.assertEqual(self.booking(time='12:00').status_code, 201)
        self.assertEqual(self.booking(time='16:00').status_code, 201)

    def test_capacity_and_inactive_table(self):
        self.assertEqual(self.booking(guests_count=5).status_code, 400)
        self.assertEqual(self.booking(guests_count=0).status_code, 400)
        self.table.is_active = False
        self.table.save()
        self.assertEqual(self.booking().status_code, 400)

    def test_hours_and_past_date(self):
        self.assertEqual(self.booking(date=str(timezone.localdate() - timedelta(days=1))).status_code, 400)
        self.assertEqual(self.booking(time='09:00').status_code, 400)
        self.assertEqual(self.booking(time='20:01').status_code, 400)
        self.assertEqual(self.booking(time='20:00').status_code, 201)

    def test_closed_day(self):
        info = RestaurantInfo.objects.get()
        info.working_hours[str(self.day.weekday())] = None
        info.save()
        self.assertEqual(self.booking().status_code, 400)

    def test_availability(self):
        self.booking()
        url = PREFIX + f'reservations/availability/?date={self.day}&time=15:00&guests=2'
        self.assertEqual(self.client.get(url).data['count'], 0)
        self.assertEqual(self.client.get(url.replace('15:00', '16:00')).data['count'], 1)
        self.assertEqual(self.client.get(PREFIX + 'reservations/availability/').status_code, 400)

    def test_early_hours_overlap(self):
        info = RestaurantInfo.objects.get()
        info.working_hours[str(self.day.weekday())] = {'open': '00:00', 'close': '22:00'}
        info.save()
        self.assertEqual(self.booking(time='00:00').status_code, 201)
        self.assertEqual(self.booking(time='01:00').status_code, 400)

    def test_owner_only_cancellation(self):
        self.login()
        booking_id = self.booking().data['id']
        self.login(self.other)
        self.assertEqual(self.client.patch(PREFIX + f'reservations/{booking_id}/cancel/').status_code, 404)
        self.assertEqual(self.client.get(PREFIX + 'reservations/').data['count'], 0)
        self.login()
        self.assertEqual(self.client.patch(PREFIX + f'reservations/{booking_id}/cancel/').status_code, 200)
        self.assertEqual(self.booking().status_code, 201)

    def test_guest_cannot_list_bookings_or_use_cart(self):
        for path in ['reservations/', 'cart/', 'orders/', 'profile/']:
            self.assertEqual(self.client.get(PREFIX + path).status_code, 401)

    def test_cart_add_merge_update_delete(self):
        self.login()
        row = self.add_dish().data['id']
        self.add_dish(3)
        cart = self.client.get(PREFIX + 'cart/').data
        self.assertEqual(len(cart['items']), 1)
        self.assertEqual(cart['items'][0]['quantity'], 5)
        self.assertEqual(cart['total_price'], '1250.00')
        self.assertEqual(self.client.patch(PREFIX + f'cart/items/{row}/', {'quantity': 4}).status_code, 200)
        self.assertEqual(self.client.delete(PREFIX + f'cart/items/{row}/').status_code, 204)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_cart_quantity_limits(self):
        self.login()
        for qty in [0, -1, 100]:
            self.assertEqual(self.add_dish(qty).status_code, 400)
        self.add_dish(99)
        self.assertEqual(self.add_dish(1).status_code, 400)
        self.assertEqual(CartItem.objects.get().quantity, 99)

    def test_other_cart_is_private(self):
        self.login()
        row = self.add_dish().data['id']
        self.login(self.other)
        self.assertEqual(self.client.patch(PREFIX + f'cart/items/{row}/', {'quantity': 9}).status_code, 404)
        self.assertEqual(self.client.delete(PREFIX + f'cart/items/{row}/').status_code, 404)

    def test_checkout_snapshots_price_and_clears_cart(self):
        self.login()
        self.add_dish()
        response = self.checkout(total_price='1.00', status='delivered')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['total_price'], '500.00')
        self.assertEqual(response.data['status'], 'new')
        self.assertFalse(CartItem.objects.exists())
        self.dish.price = Decimal('999.00')
        self.dish.save()
        order = Order.objects.get()
        self.assertEqual(order.items.get().price, Decimal('250.00'))
        self.assertEqual(order.total_price, Decimal('500.00'))

    def test_checkout_rejects_empty_cart(self):
        self.login()
        self.assertEqual(self.checkout().status_code, 400)

    def test_checkout_unavailable_rolls_back(self):
        self.login()
        self.add_dish()
        self.dish.is_available = False
        self.dish.save()
        self.assertEqual(self.checkout().status_code, 400)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(self.add_dish().status_code, 400)

    def test_delivery_address_required(self):
        self.login()
        self.add_dish()
        self.assertEqual(self.checkout(order_type='delivery', delivery_address=' ').status_code, 400)
        self.assertEqual(self.checkout(order_type='delivery', delivery_address='Бишкек, тестовый адрес').status_code, 201)

    def test_order_is_private(self):
        self.login()
        self.add_dish()
        order_id = self.checkout().data['id']
        self.login(self.other)
        self.assertEqual(self.client.get(PREFIX + f'orders/{order_id}/').status_code, 404)
        self.assertEqual(self.client.get(PREFIX + 'orders/').data['count'], 0)

    def test_nonstaff_admin_api_forbidden(self):
        self.login()
        for path in ['orders/', 'reservations/', 'reviews/', 'contact-messages/']:
            self.assertEqual(self.client.get(PREFIX + 'admin-api/' + path).status_code, 403)

    def test_order_status_transitions(self):
        self.login()
        self.add_dish()
        order_id = self.checkout().data['id']
        url = PREFIX + f'admin-api/orders/{order_id}/'
        self.assertEqual(self.client.patch(url, {'status': 'confirmed'}).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.patch(url, {'status': 'delivered'}).status_code, 400)
        for value in ['confirmed', 'cooking', 'delivered']:
            self.assertEqual(self.client.patch(url, {'status': value}).status_code, 200)
        self.assertEqual(self.client.patch(url, {'status': 'cancelled'}).status_code, 400)

    def test_cancelled_reservation_cannot_be_reopened(self):
        pk = self.booking().data['id']
        self.login(self.admin)
        url = PREFIX + f'admin-api/reservations/{pk}/'
        self.assertEqual(self.client.patch(url, {'status': 'cancelled'}).status_code, 200)
        self.assertEqual(self.client.patch(url, {'status': 'confirmed'}).status_code, 400)

    def test_review_moderation(self):
        self.login()
        response = self.client.post(PREFIX + 'reviews/', {'rating': 5, 'text': 'Всё понравилось', 'is_approved': True})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['is_approved'])
        self.assertEqual(self.client.get(PREFIX + 'reviews/').data['count'], 0)
        url = PREFIX + f"admin-api/reviews/{response.data['id']}/approve/"
        self.assertEqual(self.client.post(url).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.get(PREFIX + 'reviews/').data['count'], 1)

    def test_review_rating_and_guest_permissions(self):
        self.assertEqual(self.client.post(PREFIX + 'reviews/', {'rating': 5, 'text': 'Test'}).status_code, 401)
        self.login()
        for value in [0, 6]:
            self.assertEqual(self.client.post(PREFIX + 'reviews/', {'rating': value, 'text': 'Test'}).status_code, 400)

    def test_contact_and_admin_processing(self):
        response = self.client.post(PREFIX + 'contact/', {'name': 'Гость', 'email': 'guest@example.com', 'message': 'Вопрос'})
        self.assertEqual(response.status_code, 201)
        self.login(self.admin)
        url = PREFIX + f"admin-api/contact-messages/{response.data['id']}/"
        result = self.client.patch(url, {'is_processed': True, 'message': 'Подмена'})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(ContactMessage.objects.get().is_processed)
        self.assertEqual(ContactMessage.objects.get().message, 'Вопрос')

    def test_contact_throttle(self):
        data = {'name': 'Guest', 'email': 'g@example.com', 'message': 'Test'}
        for _ in range(5):
            self.assertEqual(self.client.post(PREFIX + 'contact/', data).status_code, 201)
        self.assertEqual(self.client.post(PREFIX + 'contact/', data).status_code, 429)

    def test_login_throttle(self):
        for _ in range(10):
            self.client.post(PREFIX + 'auth/login/', {'username': 'x', 'password': 'x'})
        self.assertEqual(self.client.post(PREFIX + 'auth/login/', {'username': 'x', 'password': 'x'}).status_code, 429)

    def test_public_info_and_docs(self):
        self.assertEqual(self.client.get(PREFIX + 'restaurant-info/').status_code, 200)
        self.assertEqual(self.client.get('/api/docs/').status_code, 200)

    def test_cors_for_frontend(self):
        result = self.client.options(PREFIX + 'menu/', HTTP_ORIGIN='http://localhost:5173', HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET')
        self.assertEqual(result['Access-Control-Allow-Origin'], 'http://localhost:5173')
