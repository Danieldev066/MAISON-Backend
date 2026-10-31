from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import (User, UserProfile, MenuCategory, MenuItem, Table, Reservation,
                     CartItem, Cart, Order, OrderItem, Review, ContactMessage, RestaurantInfo, phone_validator)
from . import services


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    phone = serializers.CharField(max_length=16, validators=[phone_validator])

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'phone']
        read_only_fields = ['id']

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Этот email уже используется.')
        return value

    def validate_phone(self, value):
        if UserProfile.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Этот телефон уже используется.')
        return value

    def validate(self, attrs):
        validate_password(attrs['password'], User(username=attrs['username'], email=attrs['email']))
        return attrs

    def create(self, validated_data):
        phone = validated_data.pop('phone')
        try:
            with transaction.atomic():
                user = User.objects.create_user(**validated_data)
                UserProfile.objects.create(user=user, phone=phone)
                Cart.objects.create(user=user)
        except IntegrityError:
            raise serializers.ValidationError('Имя, email или телефон уже используются.')
        return user

    def to_representation(self, instance):
        return ProfileSerializer(instance, context=self.context).data


class ProfileSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source='profile.phone', max_length=16, validators=[phone_validator], required=False, allow_null=False)
    avatar = serializers.ImageField(source='profile.avatar', required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'avatar']
        read_only_fields = ['id', 'username']

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=value).exists():
            raise serializers.ValidationError('Этот email уже используется.')
        return value

    def validate_phone(self, value):
        if UserProfile.objects.exclude(user=self.instance).filter(phone=value).exists():
            raise serializers.ValidationError('Этот телефон уже используется.')
        return value

    def validate_avatar(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Максимум 5 МБ.')
        return value

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        try:
            with transaction.atomic():
                instance = super().update(instance, validated_data)
                if profile_data:
                    profile = UserProfile.objects.filter(user=instance).first()
                    if profile is None:
                        if 'phone' not in profile_data:
                            raise serializers.ValidationError({'phone': 'Сначала укажите телефон.'})
                        profile = UserProfile(user=instance)
                    for key, value in profile_data.items():
                        setattr(profile, key, value)
                    profile.save()
        except IntegrityError:
            raise serializers.ValidationError('Email или телефон уже используются.')
        return instance


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'slug', 'order']


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = MenuItem
        fields = ['id', 'category', 'category_name', 'name', 'slug', 'description', 'price', 'image', 'is_vegetarian', 'is_popular', 'is_available']


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ['id', 'number', 'seats']


class AvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField()
    guests = serializers.IntegerField(min_value=1)


class ReservationSerializer(serializers.ModelSerializer):
    table_number = serializers.IntegerField(source='table.number', read_only=True)

    class Meta:
        model = Reservation
        fields = ['id', 'table', 'table_number', 'name', 'phone', 'date', 'time', 'guests_count', 'comment', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return services.create_reservation(validated_data, user if user.is_authenticated else None)


class CartItemSerializer(serializers.ModelSerializer):
    item_details = MenuItemSerializer(source='item', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'item', 'item_details', 'quantity', 'subtotal']
        read_only_fields = ['id']

    def get_subtotal(self, obj) -> str:
        return f'{obj.item.price * obj.quantity:.2f}'


class AddCartItemSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.all())
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_price']

    def get_total_price(self, obj) -> str:
        return f'{sum((row.item.price * row.quantity for row in obj.items.all()), Decimal("0")):.2f}'


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'item', 'item_name', 'quantity', 'price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'order_type', 'status', 'delivery_address', 'phone', 'comment', 'total_price', 'items', 'created_at']
        read_only_fields = ['id', 'status', 'total_price', 'items', 'created_at']

    def validate(self, attrs):
        if attrs.get('order_type') == 'delivery' and not attrs.get('delivery_address', '').strip():
            raise serializers.ValidationError({'delivery_address': 'Укажите адрес доставки.'})
        return attrs

    def create(self, validated_data):
        return services.checkout(self.context['request'].user, validated_data)


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'author', 'rating', 'text', 'is_approved', 'created_at']
        read_only_fields = ['id', 'author', 'is_approved', 'created_at']


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ['id', 'name', 'email', 'phone', 'message', 'created_at']
        read_only_fields = ['id', 'created_at']


class RestaurantInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantInfo
        fields = ['name', 'address', 'phone', 'email', 'instagram', 'facebook', 'working_hours', 'about']


class ReservationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Reservation.Status.choices)


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class AdminContactSerializer(ContactSerializer):
    class Meta(ContactSerializer.Meta):
        fields = ContactSerializer.Meta.fields + ['is_processed']
        read_only_fields = ContactSerializer.Meta.fields
