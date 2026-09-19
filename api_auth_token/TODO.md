# Token Auth

## 1. Install & Configure

```bash
pip install djangorestframework
```

Add to `settings.py`:

```python
# settings.py

INSTALLED_APPS = [
    # ...
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework.authtoken',
    'api_auth_token',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

Run migrations so the token table is created:

```bash
python manage.py migrate
```

---

## 2. Create the App

```bash
python manage.py startapp api_auth_token
```

Project structure:

```
project/
├── project/
│   ├── settings.py
│   └── urls.py
└── api_auth_token/
    ├── serializers.py
    ├── views.py
    ├── urls.py
```

---

## 3. Serializers

```python
# api_auth_token/serializers.py

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import serializers


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        if User.objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError({"email": "Email already in use."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            username=attrs.get('username'),
            password=attrs.get('password'),
        )
        if not user:
            raise serializers.ValidationError("Invalid username or password.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")
        attrs['user'] = user
        return attrs
```

---

## 4. Views

```python
# api_auth_token/views.py

from django.contrib.auth import logout
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer, LoginSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response(
                {
                    "message": "Registration successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "token": token.key,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, _ = Token.objects.get_or_create(user=user)
            return Response(
                {
                    "message": "Login successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "token": token.key,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Delete the user's token -> invalidates it forever
        request.user.auth_token.delete()
        logout(request)  # clears any session (safe no-op for pure token clients)
        return Response({"message": "Logout successful."}, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """A protected endpoint to test the token."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
        })
```

---

## 5. URLs

```python
# api_auth_token/urls.py

from django.urls import path
from .views import RegisterView, LoginView, LogoutView, ProfileView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/',    LoginView.as_view(),    name='login'),
    path('logout/',   LogoutView.as_view(),   name='logout'),
    path('profile/',  ProfileView.as_view(),  name='profile'),
]
```

```python
# project/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth_token/', include('api_auth_token.urls')),
]
```

---

## 6. How It Works

### 🔹 Register → `POST /api/auth_token/register/`

``` bash Win
curl -X POST http://127.0.0.1:8000/api/auth_token/register/ -H "Content-Type: application/json" -d "{\"username\": \"alice\", \"email\": \"alice@example.com\", \"password\": \"secret123\", \"password2\": \"secret123\"}"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_token/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "secret123",
    "password2": "secret123"
  }'
```

Response:

```json
{
  "message": "Registration successful.",
  "user": {"id": 1, "username": "alice", "email": "alice@example.com"},
  "token": "5a079ed16ff2ce59aeefe3b644a749cf21eacd73"
}
```

### 🔹 Login → `POST /api/auth_token/login/`
```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_token/login/ -H "Content-Type: application/json"  -d "{\"username\": \"alice\", \"password\": \"secret123\"}"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_token/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
```

Response:

```json
{
  "message": "Login successful.",
  "user": {"id": 1, "username": "alice", "email": "alice@example.com"},
  "token": "5a079ed16ff2ce59aeefe3b644a749cf21eacd73"
}
```

### 🔹 Access a Protected Endpoint → `GET /api/auth_token/profile/`

```bash Win
curl -X GET http://127.0.0.1:8000/api/auth_token/profile/ -H "Authorization: Token 5a079ed16ff2ce59aeefe3b644a749cf21eacd73"
```

```bash Linux/Mac
curl -X GET http://127.0.0.1:8000/api/auth_token/profile/ \
  -H "Authorization: Token 5a079ed16ff2ce59aeefe3b644a749cf21eacd73"
```

Response:

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "is_staff": false
}
```

> ⚠️ The header prefix **must** be `Token ` (not `Bearer`), unless you override `keyword` in a custom subclass.

### 🔹 Logout → `POST /api/auth_token/logout/`

```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_token/logout/ -H "Authorization: Token 5a079ed16ff2ce59aeefe3b644a749cf21eacd73"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_token/logout/ \
  -H "Authorization: Token 5a079ed16ff2ce59aeefe3b644a749cf21eacd73"
```

Response:

```json
{"message": "Logout successful."}
```

After logout the token is **deleted from the DB**. Using it again returns `401 Unauthorized`. If the user logs in again, a **new token is generated**.

---