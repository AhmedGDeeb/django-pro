Here is the equivalent full example using **Session Authentication** instead of Token or Basic Auth. Session Auth is the *stateful* approach: the server creates a session, sets a cookie, and the browser/client sends that cookie on subsequent requests.

---

# Session Auth

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
    'django.contrib.sessions',        # <-- required for Session Auth
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    # No 'rest_framework.authtoken' needed for Session Auth
    'api_auth_session',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',   # <-- required
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',              # <-- required for CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

Run migrations so the session table is created:

```bash
python manage.py migrate
```

> ⚠️ **CSRF matters here.** Because Session Auth uses cookies, DRF enforces CSRF protection on unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) when the user is authenticated via a session. For pure API clients, you'll need to obtain and send the CSRF token.

---

## 2. Create the App

```bash
python manage.py startapp api_auth_session
```

Project structure affected:

```
project/
├── project/
│   ├── settings.py
│   └── urls.py
└── api_auth_session/
    ├── serializers.py
    ├── views.py
    ├── urls.py
```

---

## 3. Serializers

```python
# api_auth_session/serializers.py

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
```

> 📝 **`login(request, user)`** — this is Django's built-in function. It writes the user's ID into the session store and sets the `sessionid` cookie on the response.

> 📝 **`logout(request)`** — flushes the session on the server and instructs the browser to delete the `sessionid` cookie.

---

## 5. URLs

```python
# api_auth_session/urls.py

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
    path('api/auth_session/', include('api_auth_session.urls')),
]
```

## 6. How It Works

### 🔹 Register → `POST /api/auth_session/register/`

```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_session/register/ -H "Content-Type: application/json" -d "{\"username\": \"alice\", \"email\": \"alice@example.com\", \"password\": \"secret123\", \"password2\": \"secret123\"}"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_session/register/ \
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
  "note": "Now call /login/ to create a session."
}
```

### 🔹 Login → `POST /api/auth_session/login/`

```bash Win
curl -X POST http://127.0.0.1:8000/api/auth_session/login/ -H "Content-Type: application/json" -d "{\"username\": \"alice\", \"password\": \"secret123\"}"

:: to save the session cookies in cookies.txt as well
curl -X POST http://127.0.0.1:8000/api/auth_session/login/ -H "Content-Type: application/json" -c cookies.txt -d "{\"username\": \"alice\", \"password\": \"secret123\"}"
```

```bash Linux/Mac
curl -X POST http://127.0.0.1:8000/api/auth_session/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
```

Response:

```json
{
  "message": "Login successful.",
  "user": {"id": 1, "username": "alice", "email": "alice@example.com"},
  "note": "A sessionid cookie has been set. Send it with subsequent requests."
}
```

> ⚠️ **Important:** With `curl`, you must **save the cookies** to a file and reuse them on subsequent requests:
> ```bash
> curl -c cookies.txt -X POST ... /login/ ...
> ```
> The `-c cookies.txt` flag tells curl to write the `sessionid` cookie to `cookies.txt`.

### 🔹 Access a Protected Endpoint → `GET /api/auth_session/profile/`

```bash Win
curl -X GET http://127.0.0.1:8000/api/auth_session/profile/ -b cookies.txt
```

```bash Linux/Mac
curl -X GET http://127.0.0.1:8000/api/auth_session/profile/ \
  -b cookies.txt
```

Response:

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "is_staff": false,
  "session_key": "abc123def456..."
}
```

> The `-b cookies.txt` flag tells curl to **read** the cookies from `cookies.txt` and send them. Without it, Django sees no `sessionid` and returns `403 Forbidden` (or `401` depending on the view).

### 🔹 Logout → `POST /api/auth_session/logout/`

⚠️ **CSRF problem:** Since `logout` is a `POST` and the user is session-authenticated, Django will reject it without a CSRF token. You have three options:

**Option A — Fetch a CSRF token first**

```bash Windows
# Login (curl saves both sessionid AND csrftoken)
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/login/ -H "Content-Type: application/json" -d "{\"username\": \"alice\", \"password\": \"secret123\"}"

# Extract csrftoken from cookies.txt and send it as X-CSRFToken
for /f "tokens=7" %A in ('findstr /i "csrftoken" cookies.txt') do curl -b cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/logout/ -H "X-CSRFToken: %A" -H "Referer: http://127.0.0.1:8000/"
```

```bash Linux/Mac
# Login (curl saves both sessionid AND csrftoken)
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'

# Extract csrftoken from cookies.txt and send it as X-CSRFToken
CSRF=$(grep csrftoken cookies.txt | awk '{print $7}')
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/logout/ \
  -H "X-CSRFToken: $CSRF" \
  -H "Referer: http://127.0.0.1:8000/"
```

**Option B — Use `@csrf_exempt` (testing only)**

```python
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(APIView):
    ...
```

> ⚠️ **Never do this in production.** It removes a crucial security layer.

**Option C — Use the DRF browsable API**

Just open `http://127.0.0.1:8000/api/auth_session/logout/` in a browser. Since DRF's browsable API handles CSRF automatically, you can click the `POST` button and it works.

Response:

```json
{
  "message": "Logout successful.",
  "note": "Session has been destroyed."
}
```

---

## 7. How the Cookie Looks

After login, Django sets a cookie like:

```
Set-Cookie: sessionid=abc123def456...; expires=...; HttpOnly; Path=/; SameSite=Lax
```

On every subsequent request, the client sends:

```
Cookie: sessionid=abc123def456...
```

That's how the server knows who you are — no token, no `Authorization` header.

---

## 8. Important Notes

| Topic | Explanation |
|---|---|
| **Stateful** | The server stores session data in `django_session` table. The client only holds a `sessionid` cookie. |
| **Logout** | Server-side: `logout(request)` flushes the session and deletes the cookie. ✅ True logout. |
| **CSRF** | Enforced on unsafe methods for session-authenticated requests. Must send `X-CSRFToken` header. |
| **CORS** | If the frontend is on a different domain, cookies won't be sent unless `credentials: 'include'` and `CORS_ALLOW_CREDENTIALS = True` are set. |
| **Mobile apps** | Awkward — mobile clients don't naturally handle cookies. Token/JWT is better for mobile. |
| **Best for** | Websites where frontend and backend share the same domain (traditional Django apps, server-rendered pages, DRF browsable API). |
| **Session expiry** | Controlled by `SESSION_COOKIE_AGE` (default 2 weeks) in `settings.py`. |

---

## 9. Session vs Token vs Basic — Side-by-Side

| Aspect | Session Auth | Token Auth | Basic Auth |
|---|---|---|---|
| **Extra package** | None | `rest_framework.authtoken` | None |
| **DB table** | `django_session` | `authtoken_token` | None |
| **Migrations** | Required | Required | Not required |
| **State** | Server-side session | Token in DB | Stateless |
| **Header / mechanism** | `Cookie: sessionid=...` | `Authorization: Token ...` | `Authorization: Basic ...` |
| **Credentials sent every request?** | ❌ Only the cookie | ❌ Only the token | ✅ Yes |
| **Can expire?** | Yes (cookie age) | No (by default) | No |
| **Revocable server-side?** | Yes (`logout()`) | Yes (delete token) | No |
| **CSRF required?** | ✅ Yes (unsafe methods) | ❌ No | ❌ No |
| **Best for** | Same-domain web apps | Mobile & SPA | Testing, internal |

---

## 10. Full Working Test Flow (Bash)

```bash Win
# 1. Register
curl -X POST http://127.0.0.1:8000/api/auth_session/register/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"email\":\"alice@example.com\",\"password\":\"secret123\",\"password2\":\"secret123\"}"

# 2. Login (saves sessionid cookie to cookies.txt)
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/login/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"secret123\"}"

# 3. Access protected endpoint (reuses the cookie)
curl -b cookies.txt http://127.0.0.1:8000/api/auth_session/profile/

# 4. Logout (needs CSRF token extracted from cookies.txt)
for /f "tokens=7" %A in ('findstr /i "csrftoken" cookies.txt') do curl -b cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/logout/ -H "X-CSRFToken: %A" -H "Referer: http://127.0.0.1:8000/"
```

```bash Mac/Linux
# 1. Register
curl -X POST http://127.0.0.1:8000/api/auth_session/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"secret123","password2":"secret123"}'

# 2. Login (saves sessionid cookie to cookies.txt)
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}'

# 3. Access protected endpoint (reuses the cookie)
curl -b cookies.txt http://127.0.0.1:8000/api/auth_session/profile/

# 4. Logout (needs CSRF token extracted from cookies.txt)
CSRF=$(grep csrftoken cookies.txt | awk '{print $7}')
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/auth_session/logout/ \
  -H "X-CSRFToken: $CSRF" \
  -H "Referer: http://127.0.0.1:8000/"
```
