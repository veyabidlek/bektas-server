@../bektas-client/AGENTS.md

# bektas-server

FastAPI backend. Python 3.13, SQLAlchemy 2.0 ORM, Pydantic v2, PostgreSQL.

## Adding a new resource

Follow this exact pattern (habits is the reference implementation):

1. **Model** → `app/models/<name>.py` — SQLAlchemy `Mapped` columns, import `Base` from `app.database`
2. **Schema** → `app/schemas/<name>.py` — Pydantic `BaseModel` for response (`Out`), create (`Create`), update (`Update`)
3. **Service** → `app/services/<name>.py` — all DB queries, takes `db: Session`, returns schema objects
4. **Router** → `app/routers/<name>.py` — thin HTTP layer, calls service functions
5. **Register model** → `app/models/__init__.py` — import so `Base.metadata.create_all()` picks it up
6. **Register router** → `app/main.py` — `app.include_router(<name>.router)`
7. **Changelog** → append a new migration block to `changelog.sql`

## Auth

- Admin-only routes: add `_: None = Depends(require_admin)` parameter (see `app/dependencies.py`)
- Login is a **key file**, not a passcode (2026-08-08). `POST /api/admin/login` takes
  multipart: either `file` (the uploaded `bekonai.key`) or `key` (its contents pasted
  as text). Both are validated identically — the file *is* the string.
- Only `sha256(secret)` is stored, in `admin_keys`. Re-issue with
  `python -m app.issue_key > bekonai.key` (stdout is the file, stderr is the log);
  issuing revokes every previous key.
- A successful login returns a 30-day JWT **and** sets it as an HttpOnly
  `bk_admin` cookie. `require_admin` / `viewer_level` accept either, so the session
  survives a cleared `localStorage` and a container restart.
- Public routes need no auth dependency

## API conventions

- All routes are prefixed `/api/<resource>`
- Response fields use **snake_case** — the frontend `transformKeys()` in `lib/api.ts` converts to camelCase automatically
- List endpoints accept `include_archived: bool = False` query param where archiving is supported
- Toggle endpoints (archive, feature) return the full updated object

## Database

- Tables are auto-created on startup via `create_tables()` in the lifespan handler
- `changelog.sql` is the human-readable schema history — **update it whenever you add or alter a table**
- Connection: `SUPABASE_DATABASE_URL` takes priority over `DATABASE_URL`

## Uploads

- Diary photos live at `/data/uploads/diary` — on the **named volume**, never in
  the image layer (`up --build` would erase them) and never in SQLite.
- Downscale on write with `app/services/image_optimize.py` (1600 px, q85). It is a
  pure function on bytes with a lazy Pillow import and never fails an upload.
- Private media is served through an **auth-checked route**, not a static mount.
  A browser cannot put an Authorization header on an `<img>` — that is what the
  HttpOnly `bk_admin` cookie is for; it rides along automatically.
- `scripts/backup.sh` captures the database *and* `/data/uploads`. Anything new
  stored on the volume has to be added there too.

## File size limits

Keep service files under 150 lines. If a service grows beyond that, split by domain.
