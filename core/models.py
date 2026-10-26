from django.db import models
from django.utils import timezone


class User(models.Model):
    user_id = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    name = models.CharField(max_length=120)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["user_id"]),
        ]

    # DRF / permission checks
    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return f"{self.email} ({self.name})"


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(default="")
    image_url = models.CharField(max_length=500, default="")
    image_public_id = models.CharField(max_length=255, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    PRODUCT_TYPES = [
        ("custom", "Custom Product"),
        ("ready_stock", "Ready Stock Product"),
    ]

    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(default="")
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES, default="custom")
    price = models.FloatField()
    offer_price = models.FloatField(null=True, blank=True)
    stock = models.IntegerField(default=0)
    image_url = models.CharField(max_length=500, default="")
    image_public_id = models.CharField(max_length=255, default="")
    additional_image_urls = models.JSONField(default=list)
    additional_image_public_ids = models.JSONField(default=list)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "products"
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["product_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_product_type_display()})"


class OfferBanner(models.Model):
    title = models.CharField(max_length=180)
    subtitle = models.CharField(max_length=255, default="")
    image_url = models.CharField(max_length=500)
    image_public_id = models.CharField(max_length=255, default="")
    link_url = models.CharField(max_length=500, default="")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "offer_banners"

    def __str__(self):
        return self.title


class WishlistItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "wishlist_items"
        indexes = [
            models.Index(fields=["user"]),
        ]


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="in_carts")
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "cart_items"
        indexes = [
            models.Index(fields=["user"]),
        ]


class Order(models.Model):
    order_id = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    name = models.CharField(max_length=120)
    email = models.EmailField()
    total = models.FloatField()
    status = models.CharField(max_length=50, default="Pending")
    payment_method = models.CharField(max_length=50)
    shipping_address = models.TextField()
    items = models.JSONField(default=list)
    attachment_url = models.CharField(max_length=500, default="")
    attachment_public_id = models.CharField(max_length=255, default="")
    coupon_code = models.CharField(max_length=50, blank=True, default="")
    discount_amount = models.FloatField(default=0.0)
    razorpay_order_id = models.CharField(max_length=100, default="")
    razorpay_payment_id = models.CharField(max_length=100, default="")
    razorpay_signature = models.CharField(max_length=255, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "orders"
        indexes = [
            models.Index(fields=["order_id"]),
            models.Index(fields=["email"]),
            models.Index(fields=["user"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Order {self.order_id} - {self.email} ({self.status})"


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.FloatField()
    min_purchase = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "coupons"
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.code} ({self.discount_percent}%)"


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="India")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "customer_addresses"
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.city}, {self.postal_code}"


class ProductReview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.IntegerField(default=5)          # Overall Rating (1-5)
    quality_rating = models.IntegerField(default=5)  # Quality Rating (1-5)
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "product_reviews"
        constraints = [
            models.UniqueConstraint(fields=["order", "product", "user"], name="unique_review_per_order_product")
        ]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["user"]),
            models.Index(fields=["order"]),
        ]

    def __str__(self):
        return f"Review by {self.user.name} for {self.product.name} ({self.rating}/5)"
