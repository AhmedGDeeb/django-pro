 JWT Auth (Multi-Device + Logout All)

## 1. Install & Configure

```bash
pip install djangorestframework djangorestframework-simplejwt
```

Add to `settings.py`:

```python
# settings.py

from datetime import timedelta

INSTALLED_APPS = [
    # ...
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',                    # JWT core
    'rest_framework_simplejwt.token_blacklist',    # <-- needed for logout / logout-all
    'api_auth_jwt',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  False,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

Run migrations so the blacklist tables are created:

```bash
python manage.py migrate
```

> 🔑 **Why blacklist matters here:** Without it, JWT is fully stateless and **logout is impossible server-side**. Enabling `token_blacklist` lets us invalidate individual refresh tokens (per-device logout) **or all of them at once** (`logout-all`).

---

## 2. Create the App

```bash
python manage.py startapp api_auth_jwt
```

Structure:

```
project/
├── project/
│   ├── settings.py
│   └── urls.py
└── api_auth_jwt/
    ├── serializers.py
    ├── views.py
    ├── urls.py
```

---

## 3. Serializers

```python
# api_auth_jwt/serializers.py

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
        return User.objects.create_user(**validated_data)


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


class LogoutSerializer(serializers.Serializer):
    """Requires the refresh token for the current device."""
    refresh = serializers.CharField()
```

---

## 4. Views

```python
# api_auth_jwt/views.py

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken, BlacklistedToken,
)

from .serializers import (
    RegisterSerializer, LoginSerializer, LogoutSerializer, EmptySerializer,
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
    serializer_class = EmptySerializer

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
        })
```

> 💡 **Key insight about `OutstandingToken`:** When the blacklist app is installed, SimpleJWT records every issued refresh token in `OutstandingToken`. That's what makes `LogoutAllView` possible — we can query all tokens for the user and blacklist them all in one shot.

---

## 5. URLs

```python
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
```

```python
# project/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth_jwt/', include('api_auth_jwt.urls')),
]
```

---

## 6. Multi-Device Behavior (Why This Works)

| Action | What happens | Other devices |
|---|---|---|
| Phone logs in | New refresh+access pair issued, stored in `OutstandingToken` | Unaffected ✅ |
| Laptop logs in | **Another** independent pair issued | Unaffected ✅ |
| Phone calls `/logout/` | Phone's refresh token is blacklisted | Laptop keeps working ✅ |
| Phone calls `/logout-all/` | **Every** refresh token for that user is blacklisted | All devices must log in again ✅ |
| Access token expires | Call `/token/refresh/` with refresh token → new access | Unaffected ✅ |

---

## 7. Full Working Test Flow (Linux / macOS Bash)

**Save tokens to files, load them for later calls.**

```bash
# 1. Register → save tokens to files
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"secret123","password2":"secret123"}' \
  > register.json

python -c "import json;d=json.load(open('register.json'));open('access.txt','w').write(d['access']);open('refresh.txt','w').write(d['refresh'])"

# 2. Login (new device) → overwrite token files
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' \
  > login.json

python -c "import json;d=json.load(open('login.json'));open('access.txt','w').write(d['access']);open('refresh.txt','w').write(d['refresh'])"

# 3. Access protected endpoint (load access token from file)
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ \
  -H "Authorization: Bearer $(cat access.txt)"

# 4. Refresh the access token (load refresh token from file)
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/token/refresh/ \
  -H "Content-Type: application/json" \
  -d "{\"refresh\":\"$(cat refresh.txt)\"}" \
  > refresh.json

python -c "import json;d=json.load(open('refresh.json'));open('access.txt','w').write(d['access'])"

# 5. Logout THIS device (blacklist its refresh token)
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout/ \
  -H "Authorization: Bearer $(cat access.txt)" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\":\"$(cat refresh.txt)\"}"

# 6. Logout ALL devices (blacklist every refresh token for this user)
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout-all/ \
  -H "Authorization: Bearer $(cat access.txt)"
```

---

## 8. Full Working Test Flow (Windows CMD)

**Same idea, but CMD has no `$(...)`, so we read files with `set /p`.**

### 1️⃣ Register → save tokens to files

```cmd
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/register/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"email\":\"alice@example.com\",\"password\":\"secret123\",\"password2\":\"secret123\"}" > register.json
```

```cmd
python -c "import json;d=json.load(open('register.json'));open('access.txt','w').write(d['access']);open('refresh.txt','w').write(d['refresh'])"
```

### 2️⃣ Login (new device) → overwrite token files

```cmd
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/login/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"secret123\"}" > login.json
```

```cmd
python -c "import json;d=json.load(open('login.json'));open('access.txt','w').write(d['access']);open('refresh.txt','w').write(d['refresh'])"
```

### 3️⃣ Load access token and call protected endpoint

```cmd
set /p ACCESS=<access.txt
```

```cmd
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer %ACCESS%"
```

### 4️⃣ Refresh the access token

```cmd
set /p REFRESH=<refresh.txt
```

```cmd
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/token/refresh/ -H "Content-Type: application/json" -d "{\"refresh\":\"%REFRESH%\"}" > refresh.json
```

```cmd
python -c "import json;d=json.load(open('refresh.json'));open('access.txt','w').write(d['access'])"
```

### 5️⃣ Logout THIS device

```cmd
set /p ACCESS=<access.txt
```

```cmd
set /p REFRESH=<refresh.txt
```

```cmd
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout/ -H "Authorization: Bearer %ACCESS%" -H "Content-Type: application/json" -d "{\"refresh\":\"%REFRESH%\"}"
```

### 6️⃣ Logout ALL devices

```cmd
set /p ACCESS=<access.txt
```

```cmd
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout-all/ -H "Authorization: Bearer %ACCESS%"
```

> ⚠️ **CMD tip:** `set /p VAR=<file` reads the first line of the file into `%VAR%`. This works because `access.txt` and `refresh.txt` are single-line strings (the JWTs).

---

## 9. Simulating Multiple Devices

To test multi-device behavior, run the login step **twice**, saving to different files:

### Bash

```bash
# Device A
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' > loginA.json
python -c "import json;d=json.load(open('loginA.json'));open('accessA.txt','w').write(d['access']);open('refreshA.txt','w').write(d['refresh'])"

# Device B
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' > loginB.json
python -c "import json;d=json.load(open('loginB.json'));open('accessB.txt','w').write(d['access']);open('refreshB.txt','w').write(d['refresh'])"

# Both tokens work in parallel
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer $(cat accessA.txt)"
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer $(cat accessB.txt)"

# Logout Device A only
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout/ \
  -H "Authorization: Bearer $(cat accessA.txt)" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\":\"$(cat refreshA.txt)\"}"

# Device B still works ✅
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer $(cat accessB.txt)"

# Now logout ALL
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout-all/ \
  -H "Authorization: Bearer $(cat accessB.txt)"
```

### Windows CMD

```cmd
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/login/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"secret123\"}" > loginA.json
python -c "import json;d=json.load(open('loginA.json'));open('accessA.txt','w').write(d['access']);open('refreshA.txt','w').write(d['refresh'])"
```

```cmd
curl -s -X POST http://127.0.0.1:8000/api/auth_jwt/login/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"secret123\"}" > loginB.json
python -c "import json;d=json.load(open('loginB.json'));open('accessB.txt','w').write(d['access']);open('refreshB.txt','w').write(d['refresh'])"
```

```cmd
set /p ACCESS_A=<accessA.txt
```

```cmd
set /p ACCESS_B=<accessB.txt
```

```cmd
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer %ACCESS_A%"
```

```cmd
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer %ACCESS_B%"
```

```cmd
set /p REFRESH_A=<refreshA.txt
```

```cmd
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout/ -H "Authorization: Bearer %ACCESS_A%" -H "Content-Type: application/json" -d "{\"refresh\":\"%REFRESH_A%\"}"
```

```cmd
curl -X GET http://127.0.0.1:8000/api/auth_jwt/profile/ -H "Authorization: Bearer %ACCESS_B%"
```

```cmd
curl -X POST http://127.0.0.1:8000/api/auth_jwt/logout-all/ -H "Authorization: Bearer %ACCESS_B%"
```

---

## 10. Files You'll See in Your Working Directory

| File | Contents |
|---|---|
| `register.json` | Full JSON response from `/register/` |
| `login.json` | Full JSON response from `/login/` |
| `loginA.json`, `loginB.json` | Responses from two different "devices" |
| `access.txt` / `accessA.txt` / `accessB.txt` | Just the **access** token (single line) |
| `refresh.txt` / `refreshA.txt` / `refreshB.txt` | Just the **refresh** token (single line) |
| `refresh.json` | Response from `/token/refresh/` |

> Add these to `.gitignore` — **never commit JWT tokens**.

---

## 11. Important Notes

| Topic | Explanation |
|---|---|
| **Multi-device by default** | Every `/login/` call issues a new refresh+access pair, so N devices can be logged in simultaneously. |
| **Per-device logout** | `/logout/` blacklists only the refresh token you send. Other devices keep working. |
| **Logout all** | `/logout-all/` blacklists every `OutstandingToken` for the user. All devices must re-authenticate. |
| **Access tokens still valid** | When you blacklist a refresh token, the already-issued **access** token remains valid until its short `exp` (e.g. 60 min). That's by design — access tokens are short-lived. |
| **`OutstandingToken`** | Only populated when `rest_framework_simplejwt.token_blacklist` is installed. That's why migrations are required. |
| **Security** | Always HTTPS. Store refresh tokens in httpOnly cookies (browser) or secure storage (mobile). Never in `localStorage` if XSS is a concern. |
| **`.gitignore`** | Add `*.txt`, `*.json`, `access*`, `refresh*` if you're testing in a repo. |

---
