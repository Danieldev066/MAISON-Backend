from datetime import time
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower

phone_validator = RegexValidator(r'^\+[1-9]\d{7,14}$', 'Телефон: +996700123456 (8–15 цифр).')


def default_hours():
    return {str(day): {'open': '10:00', 'close': '22:00'} for day in range(7)}


def validate_hours(value):
    if not isinstance(value, dict) or set(value) != set(map(str, range(7))):
        raise ValidationError('Укажите дни 0–6: понедельник–воскресенье.')
    for hours in value.values():
        if hours is None:
            continue
        try:
            start = time.fromisoformat(hours['open'])
            end = time.fromisoformat(hours['close'])
            if start.tzinfo or end.tzinfo or start >= end:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise ValidationError('График: {"open": "10:00", "close": "22:00"} или null. Ночные смены не поддерживаются.')


class User(AbstractUser):
    email = models.EmailField(unique=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='user_email_case_insensitive')]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=16, unique=True, validators=[phone_validator])
    avatar = models.ImageField(upload_to='avatars/', blank=True)

    def __str__(self):
        return self.user.username


class MenuCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name_plural = 'Menu categories'

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    image = models.ImageField(upload_to='menu/', blank=True)
    is_vegetarian = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']
        constraints = [models.CheckConstraint(condition=models.Q(price__gt=0), name='positive_menu_price')]

    def __str__(self):
        return self.name


class Table(models.Model):
    number = models.PositiveIntegerField(unique=True, validators=[MinValueValidator(1)])
    seats = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['number']
        constraints = [models.CheckConstraint(condition=models.Q(seats__gte=1), name='table_has_seats')]

    def __str__(self):
        return f'Стол {self.number} ({self.seats} мест)'


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        CONFIRMED = 'confirmed', 'Подтверждена'
        CANCELLED = 'cancelled', 'Отменена'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='reservations')
    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name='reservations')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=16, validators=[phone_validator])
    date = models.DateField()
    time = models.TimeField()
    guests_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    comment = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=12, choices=Status, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['table', 'date', 'status'])]
        constraints = [models.CheckConstraint(condition=models.Q(guests_count__gte=1), name='reservation_has_guests')]


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(99)])

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['cart', 'item'], name='unique_cart_item'),
            models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=99), name='cart_quantity_range'),
        ]


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        CONFIRMED = 'confirmed', 'Подтверждён'
        COOKING = 'cooking', 'Готовится'
        DELIVERED = 'delivered', 'Выдан / доставлен'
        CANCELLED = 'cancelled', 'Отменён'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    order_type = models.CharField(max_length=8, choices=[('delivery', 'Доставка'), ('pickup', 'Самовывоз')])
    status = models.CharField(max_length=12, choices=Status, default=Status.NEW)
    delivery_address = models.CharField(max_length=500, blank=True)
    phone = models.CharField(max_length=16, validators=[phone_validator])
    comment = models.TextField(blank=True, max_length=2000)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    item_name = models.CharField(max_length=150)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['id']


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='review_rating_range')]


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    message = models.TextField(max_length=5000)
    is_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class RestaurantInfo(models.Model):
    name = models.CharField(max_length=150, default='MAISON Restaurant')
    address = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    email = models.EmailField(blank=True)
    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    working_hours = models.JSONField(default=default_hours, validators=[validate_hours])
    about = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
