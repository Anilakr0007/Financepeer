# Financepeer

Shared finance tracking and expense splitting built with FastAPI.

## Included

- JWT account registration and login
- SQLite persistence with SQLAlchemy models
- Circles (groups), members, roles, and invitations by email
- Equal expense splitting with cent-safe remainder handling
- Spending summary, category mix, recent activity, and balances
- Settlement recording API
- Responsive dashboard served directly by FastAPI
- Interactive API docs at `/docs`

## Run locally

```powershell
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Create an account, create a circle, and add an expense.

The SQLite database is created as `financepeer.db` on first startup. Set a strong `SECRET_KEY` in `app/auth.py` before deploying.

## API shape

Authentication is via `Authorization: Bearer <token>`.

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/groups`
- `POST /api/groups`
- `POST /api/groups/{group_id}/members`
- `POST /api/expenses`
- `GET /api/expenses`
- `GET /api/summary`
- `POST /api/settlements`