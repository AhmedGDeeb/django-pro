# api_auth_basic/views.py

from django.contrib.auth import logout
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer, LoginSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "message": "Registration successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "note": "Use HTTP Basic Auth with your username/password on protected endpoints.",
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            return Response(
                {
                    "message": "Login successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "note": "No token issued — send Basic Auth header on future requests.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Basic Auth is stateless. There is no server-side state to clear,
        # so "logout" here just clears any Django session (for browsable API).
        logout(request)
        return Response(
            {
                "message": "Logout successful.",
                "note": "Client must discard stored credentials to fully log out.",
            },
            status=status.HTTP_200_OK,
        )


class ProfileView(APIView):
    """A protected endpoint to test Basic Auth."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
        })