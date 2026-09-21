# api_auth_jwt/views.py

from rest_framework import serializers, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken, BlacklistedToken,
)

from .serializers import (
    RegisterSerializer, LoginSerializer, LogoutSerializer,
)


def tokens_for_user(user):
    """Create a fresh access + refresh pair. Called on every login,
    so every device gets its own independent pair."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access":  str(refresh.access_token),
    }


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Registration successful.",
                "user": {"id": user.id, "username": user.username, "email": user.email},
                **tokens_for_user(user),          # tokens for this new device
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(generics.GenericAPIView):
    """Every successful login issues a NEW refresh+access pair.
    Nothing is stored per-user in the way DRF's Token model does,
    so N devices can be logged in simultaneously."""
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        return Response(
            {
                "message": "Login successful.",
                "user": {"id": user.id, "username": user.username, "email": user.email},
                **tokens_for_user(user),
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(generics.GenericAPIView):
    """Log out THIS device only: blacklist the refresh token that was sent.
    Other devices keep working because their refresh tokens are untouched."""
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data["refresh"]
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response(
                {"error": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"message": "Logout successful (this device only)."},
                        status=status.HTTP_200_OK)


class LogoutAllView(APIView):
    """Log out EVERY device: blacklist every outstanding refresh token
    that belongs to the current user."""
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.Serializer
    
    def post(self, request):
        tokens = OutstandingToken.objects.filter(user=request.user)
        count = 0
        for token in tokens:
            _, created = BlacklistedToken.objects.get_or_create(token=token)
            if created:
                count += 1
        return Response(
            {"message": f"Logged out from all devices. {count} token(s) blacklisted."},
            status=status.HTTP_200_OK,
        )


class ProfileView(generics.GenericAPIView):
    """Protected endpoint to test JWTs."""
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.Serializer

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
        })