from django.utils.text import slugify
from rest_framework import serializers
from .models import Category, OfferBanner, Product, User, Coupon, Address, ProductReview


class UserSerializer(serializers.Serializer):
    user_id = serializers.CharField(read_only=True)
    email = serializers.EmailField()
    name = serializers.CharField(max_length=120)
    is_staff = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=120)
    password = serializers.CharField(min_length=8, write_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class CategorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=120)
    slug = serializers.CharField(max_length=140, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.CharField(max_length=500, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        slug = attrs.get("slug") or attrs.get("name", "")
        slug = slugify(slug)
        if not slug:
            raise serializers.ValidationError({"slug": "A valid slug could not be generated from category name."})
        attrs["slug"] = slug
        return attrs


class ProductSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=180)
    slug = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    product_type = serializers.ChoiceField(choices=["custom", "ready_stock"], default="custom", required=False)
    price = serializers.FloatField(min_value=0)
    offer_price = serializers.FloatField(min_value=0, required=False, allow_null=True)
    stock = serializers.IntegerField(min_value=0, required=False)
    image_url = serializers.CharField(max_length=500, required=False, allow_blank=True)
    additional_image_urls = serializers.ListField(
        child=serializers.CharField(max_length=500),
        max_length=5,
        required=False,
        allow_empty=True,
    )
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        price = attrs.get("price")
        offer_price = attrs.get("offer_price")
        if price is not None and offer_price is not None and offer_price >= price:
            raise serializers.ValidationError({"offer_price": "Offer price must be lower than the original price."})
        slug = attrs.get("slug") or attrs.get("name", "")
        slug = slugify(slug)
        if not slug:
            raise serializers.ValidationError({"slug": "A valid slug could not be generated from product name."})
        attrs["slug"] = slug
        return attrs


class OfferBannerSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(max_length=180)
    subtitle = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.CharField(max_length=500)
    link_url = serializers.CharField(max_length=500, required=False, allow_blank=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    is_active = serializers.BooleanField(required=False)


class CouponSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField(max_length=50)
    discount_percent = serializers.FloatField(min_value=0.1, max_value=100)
    min_purchase = serializers.FloatField(min_value=0, required=False, default=0.0)
    is_active = serializers.BooleanField(required=False, default=True)
    valid_from = serializers.DateTimeField(required=False)
    valid_to = serializers.DateTimeField(required=False, allow_null=True)

    def validate_code(self, value):
        return value.strip().upper()


class AddressSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=30)
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=100, required=False, default="India")
    is_default = serializers.BooleanField(required=False, default=False)


class ProductReviewSerializer(serializers.Serializer):
    order_id = serializers.CharField()
    product_id = serializers.CharField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    quality_rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True)


def category_data(category):
    if not category:
        return None
    return {"id": str(category.id), "name": category.name, "slug": category.slug, "description": category.description, "image_url": category.image_url, "is_active": category.is_active}


def product_discount_percent(product):
    if product.offer_price is None or product.price <= 0 or product.offer_price >= product.price:
        return None
    return round(((product.price - product.offer_price) / product.price) * 100)


def product_data(product):
    return {
        "id": str(product.id),
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "product_type": getattr(product, "product_type", "custom"),
        "price": product.price,
        "offer_price": product.offer_price,
        "discount_percent": product_discount_percent(product),
        "stock": product.stock,
        "image_url": product.image_url,
        "additional_image_urls": product.additional_image_urls,
        "category": category_data(product.category),
        "is_active": product.is_active
    }


def banner_data(banner):
    return {"id": str(banner.id), "title": banner.title, "subtitle": banner.subtitle, "image_url": banner.image_url, "link_url": banner.link_url, "starts_at": banner.starts_at, "ends_at": banner.ends_at, "is_active": banner.is_active}


def wishlist_item_data(item):
    return {"id": str(item.id), "product": product_data(item.product), "created_at": item.created_at}


def cart_item_data(item):
    return {"id": str(item.id), "product": product_data(item.product), "quantity": item.quantity, "created_at": item.created_at}


def coupon_data(coupon):
    return {
        "id": str(coupon.id),
        "code": coupon.code,
        "discount_percent": coupon.discount_percent,
        "min_purchase": coupon.min_purchase,
        "is_active": coupon.is_active,
        "valid_from": coupon.valid_from.isoformat() if coupon.valid_from else None,
        "valid_to": coupon.valid_to.isoformat() if coupon.valid_to else None,
        "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
    }


def address_data(address):
    return {
        "id": str(address.id),
        "name": address.name,
        "phone": address.phone,
        "address_line1": address.address_line1,
        "address_line2": address.address_line2,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "country": address.country,
        "is_default": address.is_default,
        "created_at": address.created_at.isoformat() if address.created_at else None,
    }


def review_data(review):
    return {
        "id": str(review.id),
        "user_name": review.user.name,
        "product_id": str(review.product.id),
        "order_id": str(review.order.order_id),
        "rating": review.rating,
        "quality_rating": review.quality_rating,
        "comment": review.comment,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def order_data(order):
    return {
        "id": str(order.id),
        "order_id": order.order_id,
        "name": order.name,
        "email": order.email,
        "total": order.total,
        "status": order.status,
        "payment_method": order.payment_method,
        "shipping_address": order.shipping_address,
        "items": order.items,
        "attachment_url": order.attachment_url,
        "coupon_code": order.coupon_code,
        "discount_amount": order.discount_amount,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "user_id": str(order.user.id) if order.user else None
    }
