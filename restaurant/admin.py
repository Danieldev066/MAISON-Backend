from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from rest_framework.exceptions import ValidationError
from .models import (User, UserProfile, MenuCategory, MenuItem, Table, Reservation,
                     Cart, CartItem, Order, OrderItem, Review, ContactMessage, RestaurantInfo)
from .services import change_reservation_status, change_order_status

admin.site.site_header = 'MAISON — управление рестораном'
@admin.register(User)
class RestaurantUserAdmin(UserAdmin):
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('username', 'email', 'password1', 'password2')}),)

@admin.register(UserProfile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone']
    search_fields = ['user__username', 'phone']

class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    fields = ['name', 'slug', 'price', 'is_available']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(MenuCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_active']
    list_editable = ['order', 'is_active']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']
    inlines = [MenuItemInline]

@admin.register(MenuItem)
class MenuAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'is_popular']
    list_editable = ['price', 'is_available', 'is_popular']
    list_filter = ['category', 'is_vegetarian', 'is_available', 'is_popular']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    list_select_related = ['category']

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ['number', 'seats', 'is_active']
    list_filter = ['is_active']

class ImmutableAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

@admin.register(Reservation)
class ReservationAdmin(ImmutableAdmin):
    list_display = ['id', 'name', 'table', 'date', 'time', 'guests_count', 'status']
    list_filter = ['status', 'date', 'table']
    search_fields = ['name', 'phone']
    date_hierarchy = 'date'
    list_select_related = ['table']
    actions = ['confirm', 'cancel']
    def change_many(self, request, queryset, target):
        for pk in queryset.values_list('pk', flat=True):
            try:
                change_reservation_status(pk, target)
            except ValidationError:
                self.message_user(request, f'Бронь {pk}: переход запрещён.', messages.WARNING)
    @admin.action(description='Подтвердить выбранные брони')
    def confirm(self, request, queryset):
        self.change_many(request, queryset, 'confirmed')
    @admin.action(description='Отменить выбранные брони')
    def cancel(self, request, queryset):
        self.change_many(request, queryset, 'cancelled')

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ['item', 'item_name', 'quantity', 'price']
    readonly_fields = fields
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(ImmutableAdmin):
    list_display = ['id', 'user', 'order_type', 'status', 'total_price', 'created_at']
    list_filter = ['status', 'order_type', 'created_at']
    search_fields = ['phone', 'user__username']
    date_hierarchy = 'created_at'
    list_select_related = ['user']
    inlines = [OrderItemInline]
    actions = ['confirm', 'cook', 'deliver', 'cancel']
    def change_many(self, request, queryset, target):
        for pk in queryset.values_list('pk', flat=True):
            try:
                change_order_status(pk, target)
            except ValidationError:
                self.message_user(request, f'Заказ {pk}: переход запрещён.', messages.WARNING)
    @admin.action(description='Подтвердить заказы')
    def confirm(self, request, queryset):
        self.change_many(request, queryset, 'confirmed')
    @admin.action(description='Начать приготовление')
    def cook(self, request, queryset):
        self.change_many(request, queryset, 'cooking')
    @admin.action(description='Отметить выдачу / доставку')
    def deliver(self, request, queryset):
        self.change_many(request, queryset, 'delivered')
    @admin.action(description='Отменить заказы')
    def cancel(self, request, queryset):
        self.change_many(request, queryset, 'cancelled')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'rating', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'rating', 'created_at']
    search_fields = ['text', 'user__username']
    readonly_fields = ['created_at']
    actions = ['approve']
    @admin.action(description='Одобрить отзывы')
    def approve(self, request, queryset):
        queryset.update(is_approved=True)

@admin.register(ContactMessage)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'is_processed', 'created_at']
    list_filter = ['is_processed', 'created_at']
    search_fields = ['name', 'email', 'message']
    readonly_fields = ['name', 'email', 'phone', 'message', 'created_at']
    def has_add_permission(self, request):
        return False

@admin.register(RestaurantInfo)
class InfoAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not RestaurantInfo.objects.exists()
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Cart)
class CartAdmin(ImmutableAdmin):
    list_display = ['id', 'user']

@admin.register(CartItem)
class CartItemAdmin(ImmutableAdmin):
    list_display = ['id', 'cart', 'item', 'quantity']

@admin.register(OrderItem)
class OrderItemAdmin(ImmutableAdmin):
    list_display = ['id', 'order', 'item_name', 'quantity', 'price']
