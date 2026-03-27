# bektas-server

FastAPI backend for the personal website. PostgreSQL database, JWT admin auth.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/articles` | List articles |
| GET | `/api/articles/{slug}` | Get article + comments |
| POST | `/api/articles` | Create article (admin) |
| PUT | `/api/articles/{slug}` | Update article (admin) |
| PATCH | `/api/articles/{slug}/archive` | Archive/unarchive (admin) |
| POST | `/api/articles/{slug}/comments` | Add comment |
| DELETE | `/api/articles/{slug}/comments/{id}` | Delete comment (admin) |
| GET | `/api/habits` | List habits |
| POST | `/api/habits` | Create habit (admin) |
| PATCH | `/api/habits/{id}/archive` | Archive/unarchive (admin) |
| POST | `/api/habits/{id}/toggle` | Toggle day completion |
| GET | `/api/projects` | List pomodoro projects |
| GET | `/api/sessions` | List sessions |
| POST | `/api/sessions` | Create session |
| DELETE | `/api/sessions/{id}` | Delete session (admin) |
| GET | `/api/sessions/stats` | Focus time statistics |
| GET | `/api/about` | Get about data + profile |
| PUT | `/api/about` | Update about sections (admin) |
| GET | `/api/profile` | Get profile (tagline, bio, links) |
| PUT | `/api/profile` | Update profile (admin) |
| POST | `/api/admin/login` | Admin login (returns JWT) |
| GET | `/api/admin/verify` | Verify JWT token |

## Tech Stack

- Python 3.13, FastAPI
- PostgreSQL via SQLAlchemy
- Pydantic v2 schemas
- JWT auth with rate limiting

## Getting Started

```bash
# Start PostgreSQL
docker compose up -d

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure (edit .env with your values)
cp .env.example .env

# Seed database with mock data
python -m app.seed

# Run dev server
uvicorn app.main:app --reload --port 8000
```

Runs on http://localhost:8000. API docs at http://localhost:8000/docs.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://bektas:bektas@localhost:5432/bektas_dev` | PostgreSQL connection |
| `ADMIN_PASSCODE` | `300804` | Admin login passcode |
| `JWT_SECRET` | — | Secret for signing JWT tokens |
| `SUPABASE_DATABASE_URL` | — | Supabase connection (for sync) |

## Project Structure

```
app/
  main.py          # FastAPI app, CORS, routers
  database.py      # SQLAlchemy engine, session
  dependencies.py  # Auth middleware
  models/          # ORM models
  schemas/         # Pydantic request/response
  services/        # Business logic
  routers/         # API endpoints
  seed.py          # Mock data seeder
```
