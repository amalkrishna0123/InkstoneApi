# InkStone Django API

This backend uses Django REST Framework for HTTP APIs and standard Django ORM with SQLite3 (`db.sqlite3`).

## Setup

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Set DJANGO_SECRET_KEY, and SUPER_ADMIN_PASSWORD in .env
python manage.py migrate
python manage.py create_super_admin
python manage.py runserver 8000
```

The admin sign-in page is available at `http://localhost:8000/admin/`. The Next.js app should use `NEXT_PUBLIC_API_URL=http://localhost:8000/api`.

## API surface

- `POST /api/auth/register/`, `POST /api/auth/login/`, `POST /api/auth/refresh/`, `GET /api/auth/me/`
- `GET /api/categories/`; staff `POST`, `PATCH`, and `DELETE`
- `GET /api/products/`; staff `POST`, `PATCH`, and `DELETE` with a required category reference
- `GET /api/banners/`; staff `POST`, `PATCH`, and `DELETE`
- staff `GET /api/admin/overview/` and `GET /api/admin/users/`
- `GET /api/health/`

Access tokens expire according to `JWT_ACCESS_MINUTES`; refresh tokens expire according to `JWT_REFRESH_DAYS`. Send access tokens as `Authorization: Bearer <token>`.

For production, use HTTPS, a strong secret, restricted CORS origins, and a reverse proxy with rate limiting.