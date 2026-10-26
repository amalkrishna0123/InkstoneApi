from datetime import datetime, timedelta, timezone
import jwt
from django.conf import settings

ALGORITHM = "HS256"

def create_tokens(user):
    now = datetime.now(timezone.utc)
    access = jwt.encode({"sub": user.user_id, "type": "access", "iat": now, "exp": now + timedelta(minutes=settings.JWT_ACCESS_MINUTES)}, settings.SECRET_KEY, algorithm=ALGORITHM)
    refresh = jwt.encode({"sub": user.user_id, "type": "refresh", "iat": now, "exp": now + timedelta(days=settings.JWT_REFRESH_DAYS)}, settings.SECRET_KEY, algorithm=ALGORITHM)
    return {"access": access, "refresh": refresh, "access_expires_in": settings.JWT_ACCESS_MINUTES * 60, "refresh_expires_in": settings.JWT_REFRESH_DAYS * 86400}

def decode_token(token, token_type="access"):
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != token_type:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload
