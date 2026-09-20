Here is the equivalent full example using **Basic Authentication** instead of Token Authentication. The structure mirrors the Token example exactly, so you can compare them side by side.

---

# Basic Auth

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
    # No 'rest_framework.authtoken' needed for Basic Auth
    'api_auth_basic',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',  # for browsable API login
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

> ⚠️ **No migrations needed for Basic Auth** — it's stateless and does not store anything in the DB.

---

## 2. Create the App

```bash
python manage.py startapp api_auth_basic
```

Project structure affected:

```
project/
├── project/
│   ├── settings.py
│   └── urls.py
└── api_auth_basic/
    ├── serializers.py
    ├── views.py
    ├── urls.py
```

---

## 3. Serializers

```python
# api_auth_basic/serializers.py

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

> 📝 **Note:** `LoginSerializer` here just verifies credentials and returns the user. There is **no token to issue** — with Basic Auth, the client keeps the username + password and sends them on every request.

---

## 4. Views

```python
# api_auth_basic/views.py

from django.contrib.auth import logout
from rest_framework import status
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
            return Response(
                {
                    "message": "Registration successful.",
                    "user": {"id": user.id, "username": user.username, "email": user.email},
                    "note": "Use HTTP Basic Auth with your username/password on protected endpoints.",
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
```

---

## 5. URLs

```python
# api_auth_basic/urls.py

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
    path('api/auth_basic/', include('api_auth_basic.urls')),
]
```

---

## 6. How It Works

### 🔹 Register → `POST /api/auth_basic/register/`

```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_basic/register/ -H "Content-Type: application/json" -d "{\"username\": \"alice\", \"email\": \"alice@example.com\", \"password\": \"secret123\", \"password2\": \"secret123\"}"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_basic/register/ \
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
  "note": "Use HTTP Basic Auth with your username/password on protected endpoints."
}
```

### 🔹 Login → `POST /api/auth_basic/login/`

```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_basic/login/ -H "Content-Type: application/json" -d "{\"username\": \"alice\", \"password\": \"secret123\"}"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_basic/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
```

Response:

```json
{
  "message": "Login successful.",
  "user": {"id": 1, "username": "alice", "email": "alice@example.com"},
  "note": "No token issued — send Basic Auth header on future requests."
}
```

### 🔹 Access a Protected Endpoint → `GET /api/auth_basic/profile/`

Use curl's `-u` flag to send Basic Auth credentials:

```bash Win
curl -X GET http://127.0.0.1:8000/api/auth_basic/profile/ -u alice:secret123
```

```bash Linux/Mac
curl -X GET http://127.0.0.1:8000/api/auth_basic/profile/ \
  -u alice:secret123
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

> ℹ️ `-u alice:secret123` tells curl to Base64-encode `alice:secret123` and send it as `Authorization: Basic YWxpY2U6c2VjcmV0MTIz`.

### 🔹 Logout → `POST /api/auth_basic/logout/`

```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_basic/logout/ -u alice:secret123
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_basic/logout/ \
  -u alice:secret123
```

Response:

```json
{
  "message": "Logout successful.",
  "note": "Client must discard stored credentials to fully log out."
}
```

> ⚠️ **Key difference vs Token Auth:** With Basic Auth there is **nothing to invalidate on the server**. The credentials remain valid forever. "Logout" is entirely the client's responsibility — it must stop sending the `Authorization` header. The server-side `logout()` call only clears a Django session (relevant for the browsable API).

---

## 7. How the Authorization Header Looks

Basic Auth sends credentials as Base64-encoded `username:password`:

```
Authorization: Basic YWxpY2U6c2VjcmV0MTIz
```

You can manually build this in Bash:

```bash Linux/Mac
echo -n "alice:secret123" | base64
# -> YWxpY2U6c2VjcmV0MTIz

curl -X GET http://127.0.0.1:8000/api/auth_basic/profile/ \
  -H "Authorization: Basic YWxpY2U6c2VjcmV0MTIz"
```

``` bash Win
curl -X GET http://127.0.0.1:8000/api/auth_basic/profile/ -H "Authorization: Basic YWxpY2U6c2VjcmV0MTIz"
```

---

## 8. Important Notes

| Topic | Explanation |
|---|---|
| **Statelessness** | Basic Auth has **no login state**. Every request carries the credentials. |
| **Logout** | Not possible server-side. The client must forget the credentials. |
| **Security** | Only safe over **HTTPS**. Credentials are Base64-encoded (not encrypted), and sent on every request. |
| **Performance** | Every request re-hashes the password (bcrypt) → slower than Token Auth for high-traffic APIs. |
| **Browsable API** | When logged in via the DRF login page, `SessionAuthentication` handles the form. Otherwise the browser prompts for Basic Auth. |
| **Best use** | Quick internal tools, testing, or server-to-server calls where credentials are stored securely. |

---

## 9. Token vs Basic — Side-by-Side

| Aspect | Token Auth | Basic Auth |
|---|---|---|
| **Extra package** | `rest_framework.authtoken` | None |
| **DB table** | Yes (`authtoken_token`) | No |
| **Migrations** | Required | Not required |
| **Login endpoint** | Returns a token | Returns nothing (or just a "success") |
| **Logout endpoint** | Deletes token → invalid | No-op server-side |
| **Header on request** | `Authorization: Token <key>` | `Authorization: Basic <base64>` |
| **Credentials sent every request?** | ❌ Only the token | ✅ Username + password |
| **Can expire / rotate?** | Yes (manually) | No |
| **Revocable server-side?** | Yes | No |
| **Best for** | Mobile & SPA apps | Testing, internal tools |

---