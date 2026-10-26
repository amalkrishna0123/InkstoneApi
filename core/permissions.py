from rest_framework.permissions import BasePermission

class IsAdminUser(BasePermission):
    message = "Super admin access is required."
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_staff", False))
