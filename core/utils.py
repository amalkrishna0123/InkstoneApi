import secrets
from django.contrib.auth.hashers import check_password, make_password
from .models import User


def new_user_id():
    while True:
        value = f"INK-{secrets.token_hex(4).upper()}"
        if not User.objects.filter(user_id=value).exists():
            return value


def verify_password(raw, hashed):
    return check_password(raw, hashed)


def hash_password(raw):
    return make_password(raw)
