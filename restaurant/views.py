from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema
from .models import MenuCategory, MenuItem, Reservation, Cart, CartItem, Order, Review, ContactMessage, RestaurantInfo
from .serializers import (
    RegisterSerializer, ProfileSerializer, CategorySerializer, MenuItemSerializer,
    AvailabilitySerializer, TableSerializer, ReservationSerializer, CartSerializer,
    AddCartItemSerializer, CartItemSerializer, QuantitySerializer, OrderSerializer,
    ReviewSerializer, ContactSerializer, RestaurantInfoSerializer,
    ReservationStatusSerializer, OrderStatusSerializer, AdminContactSerializer,
)
from . import services


@extend_schema(responses={201: ProfileSerializer})
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'


class RefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user


class CategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = MenuCategory.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


class MenuViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MenuItem.objects.filter(category__is_active=True).select_related('category')
    serializer_class = MenuItemSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    filterset_fields = ['category', 'is_vegetarian', 'is_available', 'is_popular']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'name', 'id']

    @action(detail=False)
    def popular(self, request):
        items = self.filter_queryset(self.get_queryset().filter(is_popular=True, is_available=True))
        page = self.paginate_queryset(items)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class ReservationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ReservationSerializer
    queryset = Reservation.objects.select_related('table')

    def get_permissions(self):
        return [AllowAny()] if self.action in ['create', 'availability'] else [IsAuthenticated()]

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'reservation'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return self.queryset.none()
        return self.queryset.filter(user=self.request.user)

    @extend_schema(parameters=[AvailabilitySerializer], responses=TableSerializer(many=True))
    @action(detail=False, methods=['get'])
    def availability(self, request):
        params = AvailabilitySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        values = params.validated_data
        tables = services.available_tables(values['date'], values['time'], values['guests'])
        page = self.paginate_queryset(tables)
        return self.get_paginated_response(TableSerializer(page, many=True).data)

    @extend_schema(request=None, responses=ReservationSerializer)
    @action(detail=True, methods=['patch'])
    def cancel(self, request, pk=None):
        instance = self.get_object()
        result = services.change_reservation_status(instance.pk, 'cancelled')
        return Response(self.get_serializer(result).data)


class CartView(generics.RetrieveAPIView):
    serializer_class = CartSerializer

    def get_object(self):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        return Cart.objects.prefetch_related('items__item__category').get(pk=cart.pk)


class CartItemCreateView(generics.CreateAPIView):
    serializer_class = AddCartItemSerializer

    @extend_schema(responses={201: CartItemSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.add_cart_item(request.user, **serializer.validated_data)
        return Response(CartItemSerializer(row, context={'request': request}).data, status=201)


class CartItemDetailView(generics.GenericAPIView):
    serializer_class = QuantitySerializer
    queryset = CartItem.objects.all()

    @extend_schema(responses=CartItemSerializer)
    @transaction.atomic
    def patch(self, request, pk):
        cart = services.locked_cart(request.user)
        row = get_object_or_404(CartItem.objects.select_related('item__category'), cart=cart, pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row.quantity = serializer.validated_data['quantity']
        row.save(update_fields=['quantity'])
        return Response(CartItemSerializer(row, context={'request': request}).data)

    @extend_schema(request=None, responses={204: None})
    @transaction.atomic
    def delete(self, request, pk):
        cart = services.locked_cart(request.user)
        get_object_or_404(CartItem, cart=cart, pk=pk).delete()
        return Response(status=204)


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Order.objects.prefetch_related('items')
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return self.queryset.none()
        return self.queryset.filter(user=self.request.user)


class ReviewViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Review.objects.filter(is_approved=True).select_related('user')
    serializer_class = ReviewSerializer

    def get_permissions(self):
        return [AllowAny()] if self.action == 'list' else [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_approved=False)


class ContactView(generics.CreateAPIView):
    serializer_class = ContactSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'contact'


class RestaurantInfoView(generics.RetrieveAPIView):
    serializer_class = RestaurantInfoSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        return RestaurantInfo.objects.first() or RestaurantInfo()


class AdminReservationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Reservation.objects.select_related('table', 'user')
    serializer_class = ReservationSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'patch', 'head', 'options']
    filterset_fields = ['status', 'date', 'table']
    search_fields = ['name', 'phone']

    @extend_schema(request=ReservationStatusSerializer, responses=ReservationSerializer)
    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        serializer = ReservationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.change_reservation_status(obj.pk, serializer.validated_data['status'])
        return Response(self.get_serializer(obj).data)


class AdminOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Order.objects.prefetch_related('items')
    serializer_class = OrderSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'patch', 'head', 'options']
    filterset_fields = ['status', 'order_type']

    @extend_schema(request=OrderStatusSerializer, responses=OrderSerializer)
    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.change_order_status(obj.pk, serializer.validated_data['status'])
        return Response(self.get_serializer(obj).data)


class AdminReviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Review.objects.select_related('user')
    serializer_class = ReviewSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ['is_approved']

    @extend_schema(request=None, responses=ReviewSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        review = self.get_object()
        review.is_approved = True
        review.save(update_fields=['is_approved'])
        return Response(self.get_serializer(review).data)


class AdminContactViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = ContactMessage.objects.all()
    serializer_class = AdminContactSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ['get', 'patch', 'head', 'options']
    filterset_fields = ['is_processed']
    search_fields = ['name', 'email', 'message']
