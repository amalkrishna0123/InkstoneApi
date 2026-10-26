"""
This module is maintained for backward compatibility.
All models have been migrated to standard Django models in core.models.
"""
from .models import (
    User,
    Category,
    Product,
    OfferBanner,
    WishlistItem,
    CartItem,
    Order,
)

__all__ = [
    "User",
    "Category",
    "Product",
    "OfferBanner",
    "WishlistItem",
    "CartItem",
    "Order",
]
