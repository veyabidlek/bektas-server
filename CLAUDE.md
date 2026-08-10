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
- `create_all()` creates missing **tables**, never missing **columns**. A new column
  on a table that already exists in production has to be appended to
  `_ADDED_COLUMNS` in `app/database.py` (idempotent, applied at startup) *and*
  written into `changelog.sql`. Adding only the `Mapped[...]` attribute ships a
  model that its own database does not have.
- Connection: `SUPABASE_DATABASE_URL` takes priority over `DATABASE_URL`

## Uploads

- Diary photos live at `/data/uploads/diary` — on the **named volume**, never in
  the image layer (`up --build` would erase them) and never in SQLite.
- Downscale on write with `app/services/image_optimize.py` (1600 px, q85). It is a
  pure function on bytes with a lazy Pillow import and never fails an upload.
- Private media is served through an **auth-checked route**, not a static mount.
  A browser cannot put an Authorization header on an `<img>` — that is what the
  HttpOnly `bk_admin` cookie is for; it rides along automatically.
- **Portfolio screenshots** (`/data/uploads/portfolio`) are the one exception to
  the auth-checked rule: a project card is public content, so
  `GET /api/portfolio/images/{id}` has no auth dependency and is
  `Cache-Control: public`. Upload and delete stay admin-only. The row is
  **unbound to a project** on purpose — the add-project form needs a URL before
  the project exists, so `screenshot_url` only *points at* an image (an external
  URL still works).
- `scripts/backup.sh` captures the database *and* `/data/uploads`. Anything new
  stored on the volume has to be added there too.

## Habits

- A day is a **row** in `habit_completions`, and the row carries a `state` —
  `done` or `partial` (2026-08-10). A **missed day has no row**: that is how
  every read already spells "not done" (stats, streaks, the assistant's
  context), so there is no third stored value and none should be added.
- Over the API `completed_days` is `{date: true | "partial"}`. `done`
  serializes as the **boolean `true`**, never the string — the map was
  `{date: true}` before partial existed and clients truthy-check it, so that is
  the compatibility promise. Widen the domain, never re-shape the old value.
- Two writers on purpose. `POST /{id}/mark` takes `{date, state}` with
  `state ∈ done|partial|none` and **sets** (idempotent, `none` deletes the row)
  — it is the swipe tracker. `POST /{id}/toggle` is the old boolean tap and is
  **left exactly as it was**; it flips, and it clears a partial day to absent.
  Do not give `/toggle` a second meaning.
- A partial day **counts** in stats and keeps a streak alive. That is the same
  call `review_score.py` makes (`done=1, partial=½, no=0`) — nearer to done
  than to missed.
- The `date` on `/mark` is validated to literal `YYYY-MM-DD`. Neither
  `date.fromisoformat` (takes `20260810`) nor `strptime` (takes `2026-8-10`) is
  strict enough alone: a key that is not what `date.isoformat()` produces is a
  row no other read can find.

## Telegram bot

- Runs as the **`bot` compose service** — same image, `python -m app.bot`, long
  polling, no port. A bot crash must never take the website down.
- **Owner-locked** via `PERSONAL_BOT_OWNER_ID`; everyone else gets one refusal line.
- Without `PERSONAL_BOT_TOKEN` it logs why and **idles** (never exits — that would
  crash-loop under `restart: unless-stopped`).
- All capture goes through `app/services/inbox.py` + `inbox_triage.py`. Add bot
  features by extending those, not by writing a parallel path.
- Reminder delivery is idempotent via `calendar_events.reminder_fired_at`, written
  only after a successful send.
- The **evening review** (`app/bot/review.py`) asks about each of today's events at
  the time stored in the `bot_review_time` setting (default 21:30, editable on the
  calendar page) and is once-a-day via `bot_last_review_day`, the same flag shape as
  the digest. `/review` runs it on demand. A day with no events sends **nothing**.
- Review answers live in `event_outcomes` (one row per event, re-answer overwrites);
  the score math is the pure `app/services/review_score.py` — `done=1, partial=½,
  no=0` over *reviewed* events. Unanswered events never score as failures.
- The note flow is **stateless**: the prompt message carries `#ev-<event>-<card>`, and
  a reply quoting it is matched by parsing that tag. Do not add conversation state.
- The **weekly digest** (`app/bot/weekly.py`) goes out **Sunday** at `bot_weekly_digest_time`
  (default 20:00, editable on the calendar page beside the review time), once per Sunday
  via `bot_last_weekly_day`, and is switched off with `PERSONAL_BOT_WEEKLY_DIGEST=false`.
  `/digest` runs it on demand. Unlike the review it **always sends** — a week with
  nothing recorded still gets its one line.
- The week is **Monday-based, Almaty, Sunday inclusive** (`app/services/week_stats.py`,
  pure) and the counting is `app/services/weekly.py`. A Sunday belongs to the week that
  is *ending*. Add a number to the digest by adding it there, not in the copy layer.
- The digest's paragraph is DeepSeek via `app/services/llm.py` + `weekly_summary.py`.
  It is **optional by construction**: no `DEEPSEEK_API_KEY`, a timeout, a 500 or an
  empty completion all return `None` and the section is simply absent. Nothing about
  the digest may ever depend on the model answering. Model names: `deepseek-chat` is
  retired, use `deepseek-v4-flash` (the `DEEPSEEK_MODEL` default).
- Model output is **escaped** (`weekly_summary.tidy`) before it goes near Telegram —
  messages are sent with `parse_mode=HTML` and one stray `<` breaks the whole send.
- Bot copy lives in `app/bot/copy.py` and is **English** — Bektas's personal tools
  are English; the customer-facing products stay Kazakh.

## The personal assistant

- `app/services/assistant.py` reads the app and `assistant_format.py` words it —
  the same DB/pure split as `weekly.py` / `week_stats.py`. Formatting and
  arithmetic go in the pure half, where they are tested without a database.
- `build_context(db)` is the whole snapshot: now, today's and tomorrow's events,
  open tasks (overdue first, capped), habits with their **last-7-days count**,
  focus minutes **against the week before**, books in progress, open inbox.
- The tone is "honest coach", and that only stays honest because the context
  carries the counts. **Adding a claim the assistant should be able to make means
  adding the number behind it to `build_context` first** — a model asked to
  judge adherence from a single day's tick would have to guess.
- **Optional by construction**, exactly like the digest's paragraph: no
  `DEEPSEEK_API_KEY`, a timeout, a 500 or an empty completion all return `None`.
  The endpoint turns that into a **503 that says why**, never a 500.
- `POST /api/assistant/chat` is `require_admin` — it reads his private
  everything, so there is no public view of it, not even a degraded one.
- In Telegram the assistant is `/a` (alias `/ask`) and **only** that: free text
  in the bot is Inbox capture, which is load-bearing. Each `/a` is standalone —
  no conversation memory, the same statelessness the diary and review flows keep.
- The model's answer is **escaped** (`copy.assistant_reply`) before it is sent;
  messages go out with `parse_mode=HTML` and one stray `<` breaks the send.

## Universal search

- **One** FTS5 table (`search_index`), not one per model — `app/services/search_index.py`.
  `SOURCES` there is the whole specification: adding a sixth searchable thing is
  one entry, not a new table.
- Sync is by **SQLite trigger**, never by application code. Do not "also update
  the index" from a service — the triggers already caught it, and a second write
  would duplicate the row.
- `ensure_search_index()` runs from `create_tables()` and **backfills on first
  creation**. Any new source added to `SOURCES` needs the same treatment for rows
  that already exist: bump it via `POST /api/search/reindex` after deploying, or
  the old rows stay unfindable.
- User text reaches FTS5 only through `to_match_query()` in
  `app/services/search.py`, which drops everything that is not a letter or digit
  and wraps each token in quotes. **Never** interpolate a raw query into a MATCH.
- The whole feature is SQLite-only and degrades to "no results" elsewhere, never
  to a 500.

## File size limits

Keep service files under 150 lines. If a service grows beyond that, split by domain.
