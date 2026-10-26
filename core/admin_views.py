from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User
from .jwt import create_tokens
from .utils import verify_password


@csrf_exempt
def admin_dashboard(request):
    if request.method == "POST":
        import json
        try:
            data = json.loads(request.body)
            user = User.objects.filter(email=data.get("email", "").lower(), is_staff=True, is_active=True).first()
        except Exception:
            user = None
        if user and verify_password(data.get("password", ""), user.password_hash):
            tokens = create_tokens(user)
            return HttpResponse(f"<script>localStorage.setItem('inkstone_access','{tokens['access']}');location.href='/admin';</script>")
        return HttpResponse("Invalid admin credentials", status=401)
    return HttpResponse("""<!doctype html><html><head><title>InkStone Admin</title><style>body{font:16px system-ui;max-width:960px;margin:4rem auto;padding:2rem;color:#181818}main{display:grid;gap:1rem;grid-template-columns:repeat(4,1fr)}section{border:1px solid #ddd;padding:1.5rem}form{max-width:360px;display:grid;gap:.8rem}input,button{padding:.8rem;font:inherit}button{background:#111;color:white;cursor:pointer}</style></head><body><h1>InkStone Admin</h1><p>Use the protected REST dashboard APIs for categories, products, offer banners, and users.</p><form method="post"><input name="email" type="email" placeholder="Super admin email" required><input name="password" type="password" placeholder="Password" required><button>Sign in</button></form><main><section>Overview<br><code>GET /api/admin/overview/</code></section><section>Categories<br><code>CRUD /api/categories/</code></section><section>Products<br><code>CRUD /api/products/</code></section><section>Banners<br><code>CRUD /api/banners/</code></section></main></body></html>""")
