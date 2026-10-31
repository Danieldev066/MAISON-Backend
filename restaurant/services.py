from datetime import datetime, timedelta, time
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Cart, CartItem, MenuItem, Order, OrderItem, Reservation, RestaurantInfo, Table, default_hours

RESERVATION_TRANSITIONS = {'pending': {'confirmed', 'cancelled'}, 'confirmed': {'cancelled'}, 'cancelled': set()}
ORDER_TRANSITIONS = {'new': {'confirmed', 'cancelled'}, 'confirmed': {'cooking', 'cancelled'}, 'cooking': {'delivered'}, 'delivered': set(), 'cancelled': set()}


def check_booking_window(date, booking_time):
    start = timezone.make_aware(datetime.combine(date, booking_time))
    end = start + timedelta(hours=2)
    if start <= timezone.now():
        raise ValidationError({'date': 'Выберите будущее время.'})
    info = RestaurantInfo.objects.first()
    hours = (info.working_hours if info else default_hours()).get(str(date.weekday()))
    if not hours:
        raise ValidationError({'date': 'В этот день ресторан закрыт.'})
    if end.date() != date or booking_time < time.fromisoformat(hours['open']) or end.time() > time.fromisoformat(hours['close']):
        raise ValidationError({'time': 'Вся двухчасовая бронь должна попадать в часы работы.'})
    return start, end


def conflicting_reservations(date, booking_time):
    start = datetime.combine(date, booking_time)
    lower, upper = start - timedelta(hours=2), start + timedelta(hours=2)
    bookings = Reservation.objects.filter(date=date, status__in=['pending', 'confirmed'])
    if lower.date() == date:
        bookings = bookings.filter(time__gt=lower.time())
    if upper.date() == date:
        bookings = bookings.filter(time__lt=upper.time())
    return bookings


def available_tables(date, booking_time, guests):
    check_booking_window(date, booking_time)
    busy = conflicting_reservations(date, booking_time).values('table_id')
    return Table.objects.filter(is_active=True, seats__gte=guests).exclude(pk__in=busy)


@transaction.atomic
def create_reservation(data, user=None):
    table = Table.objects.select_for_update().get(pk=data['table'].pk)
    check_booking_window(data['date'], data['time'])
    if not table.is_active or table.seats < data['guests_count']:
        raise ValidationError({'table': 'Стол недоступен или недостаточно мест.'})
    if conflicting_reservations(data['date'], data['time']).filter(table=table).exists():
        raise ValidationError({'table': 'Стол уже занят на это время.'})
    return Reservation.objects.create(**data, user=user)


@transaction.atomic
def change_reservation_status(pk, target):
    reservation = Reservation.objects.select_for_update().get(pk=pk)
    if target != reservation.status:
        if target not in RESERVATION_TRANSITIONS[reservation.status]:
            raise ValidationError({'status': 'Недопустимый переход статуса брони.'})
        reservation.status = target
        reservation.save(update_fields=['status'])
    return reservation


@transaction.atomic
def change_order_status(pk, target):
    order = Order.objects.select_for_update().get(pk=pk)
    if target != order.status:
        if target not in ORDER_TRANSITIONS[order.status]:
            raise ValidationError({'status': 'Недопустимый переход статуса заказа.'})
        order.status = target
        order.save(update_fields=['status'])
    return order


def locked_cart(user):
    Cart.objects.get_or_create(user=user)
    return Cart.objects.select_for_update().get(user=user)


@transaction.atomic
def add_cart_item(user, item, quantity):
    cart = locked_cart(user)
    item = MenuItem.objects.select_for_update().select_related('category').get(pk=item.pk)
    if not item.is_available or not item.category.is_active:
        raise ValidationError({'item': 'Блюдо недоступно.'})
    row, created = CartItem.objects.get_or_create(cart=cart, item=item, defaults={'quantity': quantity})
    if not created:
        if row.quantity + quantity > 99:
            raise ValidationError({'quantity': 'Не больше 99 порций одного блюда.'})
        row.quantity += quantity
        row.save(update_fields=['quantity'])
    return row


@transaction.atomic
def checkout(user, data):
    cart = locked_cart(user)
    rows = list(cart.items.select_related('item').order_by('item_id'))
    if not rows:
        raise ValidationError({'cart': 'Корзина пуста.'})
    dishes = {dish.pk: dish for dish in MenuItem.objects.select_for_update().filter(pk__in=[r.item_id for r in rows]).select_related('category').order_by('pk')}
    for row in rows:
        dish = dishes[row.item_id]
        if not dish.is_available or not dish.category.is_active:
            raise ValidationError({'cart': f'Блюдо «{dish.name}» недоступно.'})
    total = sum((dishes[row.item_id].price * row.quantity for row in rows), Decimal('0'))
    if total > Decimal('9999999999.99'):
        raise ValidationError({'cart': 'Превышена максимальная сумма заказа.'})
    order = Order.objects.create(user=user, total_price=total, **data)
    OrderItem.objects.bulk_create([
        OrderItem(order=order, item=row.item, item_name=dishes[row.item_id].name, quantity=row.quantity, price=dishes[row.item_id].price)
        for row in rows
    ])
    cart.items.all().delete()
    return order
