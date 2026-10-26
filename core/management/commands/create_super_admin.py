import os
from django.core.management.base import BaseCommand, CommandError
from core.models import User
from core.utils import hash_password, new_user_id


class Command(BaseCommand):
    help = "Create or update the environment-configured InkStone super admin."

    def handle(self, *args, **options):
        email = os.getenv("SUPER_ADMIN_EMAIL")
        password = os.getenv("SUPER_ADMIN_PASSWORD")
        if not email or not password:
            raise CommandError("SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD are required.")

        user = User.objects.filter(email=email.lower()).first()
        if user:
            user.is_staff = True
            user.password_hash = hash_password(password)
            user.save()
        else:
            user = User.objects.create(
                user_id=new_user_id(),
                email=email.lower(),
                name="Super Admin",
                password_hash=hash_password(password),
                is_staff=True,
            )
        self.stdout.write(self.style.SUCCESS(f"Super admin ready: {email}"))
