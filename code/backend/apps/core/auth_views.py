"""
QuantYield -- Auth views

Provides the three endpoints the frontend AuthContext.jsx calls:

    POST /api/v1/auth/token/      obtain JWT access + refresh tokens
    POST /api/v1/auth/register/   create a new user account
    GET  /api/v1/auth/me/         return the authenticated user's profile

Design notes
------------
* Django's default User model uses 'username' as the login field.  We register
  every user with username == email so both fields contain the same value.
  The token view accepts { email, password } and looks up the user by email,
  bypassing the standard ModelBackend so we don't need a custom auth backend.
* All three views sit at /api/v1/auth/* which is registered directly in the
  root URLconf rather than in apps.core.urls so it stays clearly separated
  from the operational API surface.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class TokenObtainView(APIView):
    """
    POST /api/v1/auth/token/
    Body: { "email": "...", "password": "..." }
    Returns: { "access": "...", "refresh": "..." }
    """

    permission_classes = [AllowAny]
    throttle_scope = "anon"

    def post(self, request):
        email = request.data.get("email", "").strip()
        password = request.data.get("password", "")

        if not email or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prefer exact email match; fall back to username match so admin
        # accounts created via createsuperuser (which use 'admin' as username)
        # also work.
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.filter(username=email).first()

        if user is None or not user.check_password(password):
            return Response(
                {"detail": "No active account found with the given credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Body: { "email", "password", "first_name"?, "last_name"? }
    Returns: 201 with user data on success, 400 with field errors on failure.
    """

    permission_classes = [AllowAny]
    throttle_scope = "anon"

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()

        errors = {}
        if not email:
            errors["email"] = ["This field is required."]
        if not password:
            errors["password"] = ["This field is required."]
        elif len(password) < 8:
            errors["password"] = ["Password must be at least 8 characters."]

        if not errors:
            if User.objects.filter(email=email).exists():
                errors["email"] = ["A user with this email already exists."]
            if User.objects.filter(username=email).exists() and not errors.get("email"):
                errors["email"] = ["A user with this email already exists."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            username=email,  # username == email throughout the system
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    """
    GET /api/v1/auth/me/
    Requires: Authorization: Bearer <access_token>
    Returns the authenticated user's profile.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        display_name = f"{user.first_name} {user.last_name}".strip() or user.username
        initials = (
            (user.first_name[:1] + (user.last_name[:1] or user.first_name[1:2]))
            if user.first_name
            else user.email[:2]
        ).upper()

        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
                "date_joined": user.date_joined,
                "profile": {
                    "name": display_name,
                    "initials": initials,
                    "role": "Portfolio Manager" if user.is_staff else "Analyst",
                    "plan": "Enterprise" if user.is_staff else "Pro",
                },
            }
        )
