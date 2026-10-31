from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('categories', views.CategoryViewSet, basename='category')
router.register('menu', views.MenuViewSet, basename='menu')
router.register('reservations', views.ReservationViewSet, basename='reservation')
router.register('orders', views.OrderViewSet, basename='order')
router.register('reviews', views.ReviewViewSet, basename='review')
admin_router = DefaultRouter()
admin_router.register('reservations', views.AdminReservationViewSet, basename='admin-reservation')
admin_router.register('orders', views.AdminOrderViewSet, basename='admin-order')
admin_router.register('reviews', views.AdminReviewViewSet, basename='admin-review')
admin_router.register('contact-messages', views.AdminContactViewSet, basename='admin-contact')
urlpatterns = [
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/token/refresh/', views.RefreshView.as_view(), name='token-refresh'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/items/', views.CartItemCreateView.as_view(), name='cart-add'),
    path('cart/items/<int:pk>/', views.CartItemDetailView.as_view(), name='cart-item'),
    path('restaurant-info/', views.RestaurantInfoView.as_view(), name='restaurant-info'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('admin-api/', include(admin_router.urls)),
    path('', include(router.urls)),
]
