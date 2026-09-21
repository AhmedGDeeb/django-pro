# api_auth_jwt/urls.py

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, LoginView, LogoutView, LogoutAllView, ProfileView,
)

urlpatterns = [
    path('register/',   RegisterView.as_view(),   name='register'),
    path('login/',      LoginView.as_view(),      name='login'),
    path('logout/',     LogoutView.as_view(),     name='logout'),       # this device
    path('logout-all/', LogoutAllView.as_view(),  name='logout_all'),   # all devices
    path('profile/',    ProfileView.as_view(),    name='profile'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]