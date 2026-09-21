# api_auth_session/views.py

from django.contrib.auth import login, logout
from rest_framework import serializers, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer, LoginSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "message": "Registration successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "note": "Now call /login/ to create a session.",
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # This is the key step — creates the session and sets the cookie
            login(request, user)

            return Response(
                {
                    "message": "Login successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "note": "A sessionid cookie has been set. Send it with subsequent requests.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.Serializer

    def post(self, request):
        # Clears the session server-side and deletes the sessionid cookie
        logout(request)
        return Response(
            {"message": "Logout successful.", "note": "Session has been destroyed."},
            status=status.HTTP_200_OK,
        )


class ProfileView(APIView):
    """A protected endpoint to test Session Auth."""
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.Serializer

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "session_key": request.session.session_key,   # useful for debugging
        })