from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac
import os
import secrets
import uuid
import razorpay
import cloudinary.uploader
from django.conf import settings
from django.db import IntegrityError, models
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone as django_timezone
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .authentication import JWTAuthentication
from .models import Category, OfferBanner, Product, User, CartItem, WishlistItem, Order, Coupon, Address, ProductReview
from .jwt import create_tokens, decode_token
from .permissions import IsAdminUser
from .serializers import (
    CategorySerializer, LoginSerializer, OfferBannerSerializer, ProductSerializer,
    RegisterSerializer, UserSerializer, CouponSerializer, AddressSerializer, ProductReviewSerializer,
    banner_data, category_data, product_data,
    cart_item_data, wishlist_item_data, order_data,
    coupon_data, address_data, review_data
)
from .utils import hash_password, new_user_id, verify_password
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# ---------------------------------------------------------------------------
# Razorpay client – reads credentials from environment / .env via django-environ
# ---------------------------------------------------------------------------
_RAZORPAY_KEY_ID     = os.environ.get("RAZORPAY_KEY_ID", "")
_RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
_razorpay_client = razorpay.Client(auth=(_RAZORPAY_KEY_ID, _RAZORPAY_KEY_SECRET))

def user_data(user):
    return UserSerializer(user).data

def error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)

def save_fields(instance, data, excluded=()):
    for field, value in data.items():
        if field not in excluded and hasattr(instance, field):
            setattr(instance, field, value)

def get_public_id(url):
    if not url or "cloudinary.com" not in url: return ""
    try:
        parts = url.split("/upload/")
        if len(parts) < 2: return ""
        path = parts[1]
        path_parts = path.split("/")
        if path_parts[0].startswith("v") and path_parts[0][1:].isdigit():
            path_parts = path_parts[1:]
        return "/".join(path_parts).rsplit(".", 1)[0]
    except Exception:
        return ""

def local_media_path_from_url(url):
    if not url:
        return None
    try:
        media_url = settings.MEDIA_URL
        marker_index = url.find(media_url)
        if marker_index < 0:
            return None
        relative_path = url[marker_index + len(media_url):].lstrip("/\\")
        resolved_path = (settings.MEDIA_ROOT / relative_path).resolve()
        media_root = settings.MEDIA_ROOT.resolve()
        if media_root == resolved_path or media_root not in resolved_path.parents:
            return None
        return resolved_path
    except Exception:
        return None

def delete_catalog_image(url, public_id=""):
    if public_id:
        try:
            cloudinary.uploader.destroy(public_id)
            return
        except Exception:
            pass
    local_path = local_media_path_from_url(url)
    if local_path and local_path.exists():
        try:
            local_path.unlink()
        except Exception:
            pass

def save_catalog_image(request, folder):
    """Upload an image to Cloudinary. Local filesystem fallback is intentionally
    removed because Vercel's serverless environment has an ephemeral, read-only
    filesystem — files written there are lost between invocations."""
    image = request.FILES.get("image")
    if not image: return error("Please select an image.")
    if not image.content_type or not image.content_type.startswith("image/"):
        return error("Only image files are allowed.")
    if image.size > 5 * 1024 * 1024:
        return error("Image must be 5 MB or smaller.")
    extension = Path(image.name).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return error("Use a JPG, PNG, WEBP, or GIF image.")
    if not (os.getenv("CLOUDINARY_CLOUD_NAME") and os.getenv("CLOUDINARY_API_KEY") and os.getenv("CLOUDINARY_API_SECRET")):
        return error("Image storage is not configured. Please contact the administrator.", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        result = cloudinary.uploader.upload(image, folder=folder)
        return Response({"image_url": result.get("secure_url")})
    except Exception as e:
        return error(f"Upload failed: {e}", status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
def health(request):
    from django.db import connection
    try:
        connection.ensure_connection()
        return Response({"status": "ok", "database": connection.vendor})
    except Exception:
        return error("Database is unavailable.", status.HTTP_503_SERVICE_UNAVAILABLE)

@api_view(["POST"])
@authentication_classes([])
def register(request):
    serializer = RegisterSerializer(data=request.data); serializer.is_valid(raise_exception=True)
    data = serializer.validated_data; email = data["email"].lower()
    if User.objects.filter(email=email).exists(): return error("An account with this email already exists.", status.HTTP_409_CONFLICT)
    user = User.objects.create(user_id=new_user_id(), email=email, name=data["name"].strip(), password_hash=hash_password(data["password"]))
    return Response({"user": user_data(user), "tokens": create_tokens(user)}, status=status.HTTP_201_CREATED)

@api_view(["POST"])
@authentication_classes([])
def login(request):
    serializer = LoginSerializer(data=request.data); serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        user = User.objects.get(email=data["email"].lower(), is_active=True)
    except User.DoesNotExist:
        return error("Invalid email or password.", status.HTTP_401_UNAUTHORIZED)
    if not verify_password(data["password"], user.password_hash): return error("Invalid email or password.", status.HTTP_401_UNAUTHORIZED)
    return Response({"user": user_data(user), "tokens": create_tokens(user)})

@api_view(["POST"])
@authentication_classes([])
def google_login(request):
    credential = request.data.get("credential", "")
    if not credential or not settings.GOOGLE_CLIENT_ID:
        return error("Google sign in is not configured.", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        profile = id_token.verify_oauth2_token(credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
        if not profile.get("email_verified"):
            return error("Google email verification is required.", status.HTTP_400_BAD_REQUEST)
        email = profile["email"].lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            user = User.objects.create(
                user_id=new_user_id(),
                email=email,
                name=profile.get("name") or email.split("@", 1)[0],
                password_hash=hash_password(secrets.token_urlsafe(32)),
            )
    except Exception as e:
        print("GOOGLE AUTH ERROR:", e)
        return error(f"Unable to verify Google sign in: {e}", status.HTTP_401_UNAUTHORIZED)
    return Response({"user": user_data(user), "tokens": create_tokens(user)})

@api_view(["POST"])
@authentication_classes([])
def refresh(request):
    try:
        payload = decode_token(request.data.get("refresh", ""), "refresh")
        user = User.objects.get(user_id=payload["sub"], is_active=True)
    except Exception:
        return error("Invalid or expired refresh token.", status.HTTP_401_UNAUTHORIZED)
    return Response({"tokens": create_tokens(user)})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({"user": user_data(request.user)})

@api_view(["GET", "POST"])
def categories(request):
    if request.method == "GET": return Response([category_data(item) for item in Category.objects.filter(is_active=True).order_by("name")])
    if not IsAdminUser().has_permission(request, None): return error("Super admin access is required.", status.HTTP_403_FORBIDDEN)
    serializer = CategorySerializer(data=request.data); serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if "image_url" in data: data["image_public_id"] = get_public_id(data["image_url"])
    try:
        category = Category.objects.create(**data)
        return Response(category_data(category), status=status.HTTP_201_CREATED)
    except Exception: return error("Category name or slug already exists.", status.HTTP_409_CONFLICT)

@api_view(["POST"])
@permission_classes([IsAdminUser])
def upload_category_image(request):
    return save_catalog_image(request, "category-images")

@api_view(["POST"])
@permission_classes([IsAdminUser])
def upload_product_image(request):
    return save_catalog_image(request, "product-images")

@api_view(["POST"])
@permission_classes([IsAdminUser])
def upload_banner_image(request):
    return save_catalog_image(request, "banner-images")

@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def category_detail(request, category_id):
    try: category = Category.objects.get(id=category_id)
    except Category.DoesNotExist: return error("Category not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        if Product.objects.filter(category=category).exists(): return error("Move or delete products before removing this category.")
        delete_catalog_image(category.image_url, category.image_public_id)
        category.delete(); return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = CategorySerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True); data = serializer.validated_data
    if "image_url" in data and data["image_url"] != category.image_url:
        delete_catalog_image(category.image_url, category.image_public_id)
        data["image_public_id"] = get_public_id(data["image_url"])
    save_fields(category, data); category.updated_at = django_timezone.now(); category.save(); return Response(category_data(category))

def resolve_category(category_input):
    if not category_input:
        return None
    try:
        if isinstance(category_input, int) or (isinstance(category_input, str) and category_input.isdigit()):
            cat = Category.objects.filter(id=int(category_input)).first()
            if cat: return cat
        if isinstance(category_input, str):
            cat = Category.objects.filter(models.Q(slug=category_input) | models.Q(name=category_input)).first()
            if cat: return cat
    except Exception:
        pass
    return None

@api_view(["GET", "POST"])
def products(request):
    if request.method == "GET":
        items = Product.objects.filter(is_active=True).select_related("category")
        if request.query_params.get("category"):
            items = items.filter(category_id=request.query_params["category"])
        if request.query_params.get("product_type"):
            items = items.filter(product_type=request.query_params["product_type"])
        return Response([product_data(item) for item in items.order_by("-created_at")])
    if not IsAdminUser().has_permission(request, None): return error("Super admin access is required.", status.HTTP_403_FORBIDDEN)
    serializer = ProductSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
    cat_input = data.pop("category", None)
    category = resolve_category(cat_input) if cat_input else None
    product_type = data.get("product_type", "custom")
    if product_type == "custom" and not category:
        return error("A valid category is required for custom products.")
    if "image_url" in data: data["image_public_id"] = get_public_id(data["image_url"])
    if "additional_image_urls" in data: data["additional_image_public_ids"] = [get_public_id(url) for url in data["additional_image_urls"]]
    try:
        product = Product.objects.create(category=category, **data)
        return Response(product_data(product), status=status.HTTP_201_CREATED)
    except IntegrityError:
        return error("A product with this slug already exists. Please choose a different name or slug.", status.HTTP_409_CONFLICT)
    except Exception as e:
        return error(f"Failed to create product: {e}", status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
def public_product_detail(request, product_id):
    """Public endpoint — returns a single active product by ID, plus related products from the same category."""
    try:
        product = Product.objects.select_related("category").get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        return error("Product not found.", status.HTTP_404_NOT_FOUND)
    data = product_data(product)
    # Include up to 8 related products from the same category or same product_type (excluding self)
    if product.category:
        related = Product.objects.filter(category=product.category, is_active=True).select_related("category").order_by("-created_at").exclude(id=product_id)
    else:
        related = Product.objects.filter(product_type=product.product_type, is_active=True).select_related("category").order_by("-created_at").exclude(id=product_id)
    data["related_products"] = [product_data(p) for p in related[:8]]
    return Response(data)

@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def product_detail(request, product_id):
    try: product = Product.objects.select_related("category").get(id=product_id)
    except Product.DoesNotExist: return error("Product not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        delete_catalog_image(product.image_url, product.image_public_id)
        for index, url in enumerate(product.additional_image_urls):
            public_id = product.additional_image_public_ids[index] if index < len(product.additional_image_public_ids) else ""
            delete_catalog_image(url, public_id)
        product.delete(); return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = ProductSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True); data = serializer.validated_data
    if "category" in data:
        cat_input = data["category"]
        if cat_input:
            cat = resolve_category(cat_input)
            if not cat: return error("A valid category is required.")
            data["category"] = cat
        else:
            data["category"] = None
    target_type = data.get("product_type", product.product_type)
    target_category = data.get("category", product.category)
    if target_type == "custom" and not target_category:
        return error("A valid category is required for custom products.")
    effective_price = data.get("price", product.price)
    effective_offer_price = data.get("offer_price", product.offer_price)
    if effective_offer_price is not None and effective_offer_price >= effective_price:
        return error("Offer price must be lower than the original price.")
    if "image_url" in data and data["image_url"] != product.image_url:
        delete_catalog_image(product.image_url, product.image_public_id)
        data["image_public_id"] = get_public_id(data["image_url"])
    if "additional_image_urls" in data:
        next_public_ids = {get_public_id(url) for url in data["additional_image_urls"]}
        next_urls = set(data["additional_image_urls"])
        for index, url in enumerate(product.additional_image_urls):
            public_id = product.additional_image_public_ids[index] if index < len(product.additional_image_public_ids) else ""
            if public_id not in next_public_ids and url not in next_urls:
                delete_catalog_image(url, public_id)
        data["additional_image_public_ids"] = [get_public_id(url) for url in data["additional_image_urls"]]
    save_fields(product, data)
    product.updated_at = django_timezone.now()
    try:
        product.save()
    except IntegrityError:
        return error("A product with this slug already exists. Please choose a different name or slug.", status.HTTP_409_CONFLICT)
    except Exception as e:
        return error(f"Failed to update product: {e}", status.HTTP_400_BAD_REQUEST)
    return Response(product_data(product))

@api_view(["GET", "POST"])
def banners(request):
    if request.method == "GET": return Response([banner_data(item) for item in OfferBanner.objects.filter(is_active=True).order_by("-created_at")])
    if not IsAdminUser().has_permission(request, None): return error("Super admin access is required.", status.HTTP_403_FORBIDDEN)
    serializer = OfferBannerSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
    if data["ends_at"] <= data["starts_at"]: return error("Banner end time must be after its start time.")
    if "image_url" in data: data["image_public_id"] = get_public_id(data["image_url"])
    banner = OfferBanner.objects.create(**data)
    return Response(banner_data(banner), status=status.HTTP_201_CREATED)

@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def banner_detail(request, banner_id):
    try: banner = OfferBanner.objects.get(id=banner_id)
    except OfferBanner.DoesNotExist: return error("Banner not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        delete_catalog_image(banner.image_url, banner.image_public_id)
        banner.delete(); return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = OfferBannerSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True); data = serializer.validated_data
    if "image_url" in data and data["image_url"] != banner.image_url:
        delete_catalog_image(banner.image_url, banner.image_public_id)
        data["image_public_id"] = get_public_id(data["image_url"])
    save_fields(banner, data); banner.save(); return Response(banner_data(banner))

@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_overview(request):
    return Response({"users": User.objects.count(), "categories": Category.objects.count(), "products": Product.objects.count(), "banners": OfferBanner.objects.count()})

@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_users(request):
    return Response([user_data(user) for user in User.objects.order_by("-created_at")])

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def wishlist_view(request):
    if request.method == "GET":
        items = WishlistItem.objects.filter(user=request.user).select_related("product__category").order_by("-created_at")
        return Response([wishlist_item_data(item) for item in items])

    product_id = request.data.get("product_id")
    if not product_id:
        return error("product_id is required.")
    try:
        product = Product.objects.get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        return error("Product not found.", status.HTTP_404_NOT_FOUND)

    existing = WishlistItem.objects.filter(user=request.user, product=product).first()
    if existing:
        existing.delete()
        return Response({"status": "removed", "product_id": product_id})
    else:
        item = WishlistItem.objects.create(user=request.user, product=product)
        return Response({"status": "added", "item": wishlist_item_data(item)}, status=status.HTTP_201_CREATED)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def wishlist_detail_view(request, item_id):
    try:
        item = WishlistItem.objects.get(id=item_id, user=request.user)
    except WishlistItem.DoesNotExist:
        return error("Wishlist item not found.", status.HTTP_404_NOT_FOUND)
    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def cart_view(request):
    if request.method == "GET":
        items = CartItem.objects.filter(user=request.user).select_related("product__category").order_by("-created_at")
        return Response([cart_item_data(item) for item in items])

    product_id = request.data.get("product_id")
    quantity = int(request.data.get("quantity", 1))
    if not product_id:
        return error("product_id is required.")
    try:
        product = Product.objects.get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        return error("Product not found.", status.HTTP_404_NOT_FOUND)

    existing = CartItem.objects.filter(user=request.user, product=product).first()
    if existing:
        existing.quantity += quantity
        if existing.quantity <= 0:
            existing.delete()
            return Response({"status": "removed", "product_id": product_id})
        existing.updated_at = django_timezone.now()
        existing.save()
        return Response(cart_item_data(existing))
    else:
        if quantity <= 0:
            quantity = 1
        item = CartItem.objects.create(user=request.user, product=product, quantity=quantity)
        return Response(cart_item_data(item), status=status.HTTP_201_CREATED)

@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def cart_detail_view(request, item_id):
    try:
        item = CartItem.objects.select_related("product__category").get(id=item_id, user=request.user)
    except CartItem.DoesNotExist:
        return error("Cart item not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    quantity = request.data.get("quantity")
    if quantity is not None:
        quantity = int(quantity)
        if quantity <= 0:
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        item.quantity = quantity
        item.updated_at = django_timezone.now()
        item.save()
    return Response(cart_item_data(item))

@api_view(["POST"])
@authentication_classes([])  # Allow unauthenticated upload
def upload_order_attachment(request):
    return save_catalog_image(request, "order-attachments")


@api_view(["POST"])
@authentication_classes([])  # Allow guest checkout
def create_order(request):
    """Create an internal Order and a corresponding Razorpay order."""
    data = request.data

    total_inr = float(data.get("total", 0))
    amount_paise = int(round(total_inr * 100))
    if amount_paise < 100:
        return error("Order amount must be at least ₹1 (100 paise).", status.HTTP_400_BAD_REQUEST)

    order_id = f"CR-{uuid.uuid4().hex[:6].upper()}"

    user = None
    if request.user and request.user.is_authenticated:
        user = request.user
    elif data.get("email"):
        user = User.objects.filter(email=data.get("email")).first()

    # ── Create Razorpay order ────────────────────────────────────────────────
    try:
        rz_order = _razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": order_id,
            "payment_capture": 1,
        })
    except Exception as e:
        return error(f"Razorpay error: {e}", status.HTTP_502_BAD_GATEWAY)

    # ── Save to our database ─────────────────────────────────────────────────
    try:
        order = Order.objects.create(
            order_id=order_id,
            user=user,
            name=data.get("name"),
            email=data.get("email"),
            total=total_inr,
            status="Pending",
            payment_method=data.get("payment_method", "Razorpay"),
            shipping_address=data.get("shipping_address", ""),
            items=data.get("items", []),
            attachment_url=data.get("attachment_url", ""),
            attachment_public_id=get_public_id(data.get("attachment_url", "")) if data.get("attachment_url") else "",
            coupon_code=data.get("coupon_code", ""),
            discount_amount=float(data.get("discount_amount", 0.0)),
            razorpay_order_id=rz_order["id"],
        )
        result = order_data(order)
        result["razorpay_order_id"] = rz_order["id"]
        result["amount"] = amount_paise
        result["currency"] = "INR"
        return Response(result, status=status.HTTP_201_CREATED)
    except Exception as e:
        return error(str(e))


@api_view(["POST"])
@authentication_classes([])
def verify_payment(request):
    """Verify Razorpay payment signature and mark order as Paid."""
    data = request.data

    razorpay_order_id  = data.get("razorpay_order_id",  "")
    razorpay_payment_id = data.get("razorpay_payment_id", "")
    razorpay_signature  = data.get("razorpay_signature",  "")

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return error("Missing payment verification fields.", status.HTTP_400_BAD_REQUEST)

    # ── Verify HMAC-SHA256 signature ─────────────────────────────────────────
    try:
        _razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id":   razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature":  razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return error("Payment signature verification failed.", status.HTTP_400_BAD_REQUEST)

    # ── Update order in DB ───────────────────────────────────────────────────
    try:
        order = Order.objects.get(razorpay_order_id=razorpay_order_id)
        order.razorpay_payment_id = razorpay_payment_id
        order.razorpay_signature  = razorpay_signature
        order.status = "Paid"
        order.save()
        return Response({"status": "success", "order_id": order.order_id})
    except Exception as e:
        return error(str(e))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_orders(request):
    orders = Order.objects.order_by("-created_at")
    return Response([order_data(o) for o in orders])


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def admin_update_order_status(request, order_id):
    try:
        order = Order.objects.get(models.Q(id=order_id) | models.Q(order_id=order_id))
    except Order.DoesNotExist:
        return error("Order not found.", status.HTTP_404_NOT_FOUND)
    new_status = request.data.get("status")
    if not new_status:
        return error("Status is required.")
    order.status = new_status
    order.save()
    return Response(order_data(order))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    orders = Order.objects.filter(models.Q(user=request.user) | models.Q(email=request.user.email)).order_by("-created_at")
    return Response([order_data(o) for o in orders])


# ─── Coupon Management Endpoints ─────────────────────────────────────────────
@api_view(["GET", "POST"])
def admin_coupons(request):
    if not IsAdminUser().has_permission(request, None):
        return error("Super admin access is required.", status.HTTP_403_FORBIDDEN)
    if request.method == "GET":
        coupons = Coupon.objects.all().order_by("-created_at")
        return Response([coupon_data(c) for c in coupons])
    serializer = CouponSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        coupon = Coupon.objects.create(**serializer.validated_data)
        return Response(coupon_data(coupon), status=status.HTTP_201_CREATED)
    except IntegrityError:
        return error("A coupon with this code already exists.", status.HTTP_409_CONFLICT)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def admin_coupon_detail(request, coupon_id):
    try:
        coupon = Coupon.objects.get(id=coupon_id)
    except Coupon.DoesNotExist:
        return error("Coupon not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        coupon.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = CouponSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    save_fields(coupon, serializer.validated_data)
    coupon.save()
    return Response(coupon_data(coupon))


@api_view(["POST"])
@authentication_classes([])
def validate_coupon(request):
    code = (request.data.get("code") or "").strip().upper()
    try:
        subtotal = float(request.data.get("subtotal", 0))
    except (ValueError, TypeError):
        subtotal = 0.0
    if not code:
        return error("Please enter a coupon code.")
    try:
        coupon = Coupon.objects.get(code__iexact=code, is_active=True)
    except Coupon.DoesNotExist:
        return error("Invalid or inactive coupon code.", status.HTTP_404_NOT_FOUND)

    now = django_timezone.now()
    if coupon.valid_from and now < coupon.valid_from:
        return error("This coupon is not active yet.")
    if coupon.valid_to and now > coupon.valid_to:
        return error("This coupon has expired.")
    if subtotal < coupon.min_purchase:
        return error(f"Minimum order amount for this coupon is Rs. {coupon.min_purchase:.2f}")

    discount_amount = round((subtotal * coupon.discount_percent) / 100.0, 2)
    return Response({
        "valid": True,
        "code": coupon.code,
        "discount_percent": coupon.discount_percent,
        "discount_amount": discount_amount,
        "min_purchase": coupon.min_purchase,
    })


# ─── Customer Address Endpoints ──────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def customer_addresses(request):
    if request.method == "GET":
        addrs = Address.objects.filter(user=request.user).order_by("-is_default", "-created_at")
        return Response([address_data(a) for a in addrs])
    serializer = AddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if data.get("is_default"):
        Address.objects.filter(user=request.user).update(is_default=False)
    elif not Address.objects.filter(user=request.user).exists():
        data["is_default"] = True
    addr = Address.objects.create(user=request.user, **data)
    return Response(address_data(addr), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def customer_address_detail(request, address_id):
    try:
        addr = Address.objects.get(id=address_id, user=request.user)
    except Address.DoesNotExist:
        return error("Address not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        was_default = addr.is_default
        addr.delete()
        if was_default:
            next_addr = Address.objects.filter(user=request.user).first()
            if next_addr:
                next_addr.is_default = True
                next_addr.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = AddressSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if data.get("is_default"):
        Address.objects.filter(user=request.user).exclude(id=addr.id).update(is_default=False)
    save_fields(addr, data)
    addr.save()
    return Response(address_data(addr))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def customer_address_default(request, address_id):
    try:
        addr = Address.objects.get(id=address_id, user=request.user)
    except Address.DoesNotExist:
        return error("Address not found.", status.HTTP_404_NOT_FOUND)
    Address.objects.filter(user=request.user).update(is_default=False)
    addr.is_default = True
    addr.save()
    return Response(address_data(addr))


# ─── Product Reviews Endpoints ───────────────────────────────────────────────
@api_view(["GET"])
def product_reviews(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return error("Product not found.", status.HTTP_404_NOT_FOUND)
    reviews = ProductReview.objects.filter(product=product).select_related("user", "order").order_by("-created_at")
    data = [review_data(r) for r in reviews]
    count = len(data)
    avg_rating = round(sum(r["rating"] for r in data) / count, 1) if count > 0 else 0
    avg_quality = round(sum(r["quality_rating"] for r in data) / count, 1) if count > 0 else 0
    return Response({
        "reviews": data,
        "total": count,
        "average_rating": avg_rating,
        "average_quality_rating": avg_quality,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_product_review(request):
    serializer = ProductReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # Find order
    try:
        order = Order.objects.get(
            models.Q(id=data["order_id"]) | models.Q(order_id=data["order_id"]),
            models.Q(user=request.user) | models.Q(email=request.user.email)
        )
    except Order.DoesNotExist:
        return error("Order not found or does not belong to your account.", status.HTTP_404_NOT_FOUND)

    # Ensure order has been delivered
    if order.status.lower() != "delivered":
        return error("Reviews can only be submitted after your order has been successfully delivered.", status.HTTP_400_BAD_REQUEST)

    # Find product
    try:
        product = Product.objects.get(id=data["product_id"])
    except Product.DoesNotExist:
        return error("Product not found.", status.HTTP_404_NOT_FOUND)

    # Verify product is in order items
    product_in_order = any(
        str(item.get("product_id")) == str(product.id) or str(item.get("id")) == str(product.id)
        for item in order.items
    )
    if not product_in_order:
        return error("This product was not part of the specified order.")

    # Check if already reviewed
    if ProductReview.objects.filter(order=order, product=product, user=request.user).exists():
        return error("You have already reviewed this product for this order.", status.HTTP_409_CONFLICT)

    review = ProductReview.objects.create(
        user=request.user,
        order=order,
        product=product,
        rating=data["rating"],
        quality_rating=data["quality_rating"],
        comment=data.get("comment", "").strip()
    )
    return Response(review_data(review), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_reviews(request):
    delivered_orders = Order.objects.filter(
        models.Q(user=request.user) | models.Q(email=request.user.email),
        status__iexact="delivered"
    ).order_by("-created_at")

    reviewed_pairs = set(
        ProductReview.objects.filter(user=request.user).values_list("order_id", "product_id")
    )

    pending = []
    for order in delivered_orders:
        for item in order.items:
            p_id = item.get("product_id") or item.get("id")
            if p_id:
                try:
                    p_id_int = int(p_id)
                except ValueError:
                    p_id_int = p_id
                if (order.id, p_id_int) not in reviewed_pairs:
                    pending.append({
                        "order_id": order.order_id,
                        "order_db_id": str(order.id),
                        "product_id": str(p_id),
                        "product_name": item.get("name", "Product"),
                        "product_image": item.get("image_url", ""),
                        "price": item.get("price", 0),
                    })
    return Response(pending)
