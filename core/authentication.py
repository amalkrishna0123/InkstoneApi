from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .jwt import decode_token
from .models import User


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        try:
            payload = decode_token(header[7:])
            user = User.objects.get(user_id=payload["sub"], is_active=True)
        except Exception as exc:
            # Returning None instead of raising AuthenticationFailed allows DRF to fallback
            # to AnonymousUser, ensuring that @permission_classes([AllowAny]) endpoints
            # still work even if the client sends an expired token.
            return None
        return user, payload
