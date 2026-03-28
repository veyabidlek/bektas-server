# bektas-server

FastAPI backend for the personal website. PostgreSQL database, JWT admin auth.

## API Endpoints

### Articles
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/articles` | — | List articles |
| GET | `/api/articles/{slug}` | — | Get article + comments |
| POST | `/api/articles` | admin | Create article |
| PUT | `/api/articles/{slug}` | admin | Update article |
| PATCH | `/api/articles/{slug}/archive` | admin | Archive/unarchive |
| POST | `/api/articles/{slug}/comments` | — | Add comment |
| DELETE | `/api/articles/{slug}/comments/{id}` | admin | Delete comment |

### Habits
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/habits` | — | List habits |
| POST | `/api/habits` | admin | Create habit |
| PATCH | `/api/habits/{id}/archive` | admin | Archive/unarchive |
| POST | `/api/habits/{id}/toggle` | — | Toggle day completion |

### Portfolio Projects
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/portfolio` | — | List portfolio projects |
| POST | `/api/portfolio` | admin | Create project |
| PUT | `/api/portfolio/{id}` | admin | Update project |
| PATCH | `/api/portfolio/{id}/archive` | admin | Archive/unarchive |
| PATCH | `/api/portfolio/{id}/feature` | admin | Toggle featured (gold ring) |

### Pomodoro
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/projects` | — | List pomodoro projects |
| GET | `/api/sessions` | — | List sessions |
| POST | `/api/sessions` | — | Create session |
| DELETE | `/api/sessions/{id}` | admin | Delete session |
| GET | `/api/sessions/stats` | — | Focus time statistics |

### Profile & About
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/about` | — | Get about data + profile |
| PUT | `/api/about` | admin | Update about sections |
| GET | `/api/profile` | — | Get profile (tagline, bio, links) |
| PUT | `/api/profile` | admin | Update profile |

### Admin
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/admin/login` | — | Login, returns JWT |
| GET | `/api/admin/verify` | — | Verify JWT token |

## Tech Stack

- Python 3.13, FastAPI
- PostgreSQL via SQLAlchemy 2.0
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

# Configure
cp .env.example .env  # edit with your values

# Seed database with mock data
python -m app.seed

# Run dev server
uvicorn app.main:app --reload --port 8000
```

Runs on http://localhost:8000. Swagger docs at http://localhost:8000/docs.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://bektas:bektas@localhost:5432/bektas_dev` | PostgreSQL connection |
| `SUPABASE_DATABASE_URL` | — | Supabase connection (takes priority over DATABASE_URL) |
| `ADMIN_PASSCODE` | `300804` | Admin login passcode |
| `JWT_SECRET` | — | Secret for signing JWT tokens |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

## Project Structure

```
app/
  main.py          # FastAPI app, CORS, router registration
  database.py      # SQLAlchemy engine, session, Base
  dependencies.py  # require_admin auth dependency
  models/          # ORM models (one file per domain)
  schemas/         # Pydantic request/response types
  services/        # Business logic (DB queries)
  routers/         # HTTP endpoints (thin layer over services)
  seed.py          # Mock data seeder
changelog.sql      # Full schema history (update on every table change)
```
