-- =============================================================================
-- Database Changelog
-- Engine: PostgreSQL (Supabase)
-- Each migration is idempotent (CREATE TABLE IF NOT EXISTS).
-- Run migrations in order when setting up a fresh database.
-- SQLAlchemy auto-creates tables on startup via Base.metadata.create_all(),
-- so these are the reference source of truth for schema history.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Migration 001 — Initial schema
-- Date: 2026-03-01
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS articles (
    slug        VARCHAR PRIMARY KEY,
    title       VARCHAR NOT NULL,
    description TEXT    NOT NULL,
    date        VARCHAR NOT NULL,
    read_time   VARCHAR NOT NULL,
    body        JSONB   NOT NULL,
    archived    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS comments (
    id           VARCHAR PRIMARY KEY,
    article_slug VARCHAR NOT NULL REFERENCES articles(slug) ON DELETE CASCADE,
    author       VARCHAR NOT NULL,
    avatar       VARCHAR NOT NULL,
    date         VARCHAR NOT NULL,
    body         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS habits (
    id       VARCHAR PRIMARY KEY,
    name     VARCHAR NOT NULL,
    emoji    VARCHAR NOT NULL,
    color    VARCHAR NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS habit_completions (
    id       SERIAL  PRIMARY KEY,
    habit_id VARCHAR NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    date     VARCHAR NOT NULL,
    CONSTRAINT uq_habit_date UNIQUE (habit_id, date)
);

CREATE TABLE IF NOT EXISTS projects (
    id    VARCHAR PRIMARY KEY,
    name  VARCHAR NOT NULL,
    color VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS pomodoro_sessions (
    id               VARCHAR PRIMARY KEY,
    project_id       VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    description      VARCHAR NOT NULL,
    started_at       VARCHAR NOT NULL,
    duration_minutes INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS experience_items (
    id          SERIAL  PRIMARY KEY,
    company     VARCHAR NOT NULL,
    role        VARCHAR NOT NULL,
    period      VARCHAR NOT NULL,
    description TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skill_categories (
    id         SERIAL  PRIMARY KEY,
    title      VARCHAR NOT NULL,
    skills     JSONB   NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS education_items (
    id          SERIAL  PRIMARY KEY,
    institution VARCHAR NOT NULL,
    degree      VARCHAR NOT NULL,
    period      VARCHAR NOT NULL,
    note        VARCHAR,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile (
    id           INTEGER PRIMARY KEY DEFAULT 1,
    tagline      VARCHAR NOT NULL DEFAULT '',
    short_bio    TEXT    NOT NULL DEFAULT '',
    long_bio     JSONB   NOT NULL DEFAULT '[]',
    social_links JSONB   NOT NULL DEFAULT '[]'
);


-- -----------------------------------------------------------------------------
-- Migration 002 — Portfolio projects
-- Date: 2026-03-28
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS portfolio_projects (
    id             VARCHAR PRIMARY KEY,
    title          VARCHAR NOT NULL,
    description    VARCHAR NOT NULL DEFAULT '',
    screenshot_url VARCHAR,
    website_url    VARCHAR,
    github_url     VARCHAR,
    stack          JSONB   NOT NULL DEFAULT '[]',
    featured       BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    archived       BOOLEAN NOT NULL DEFAULT FALSE
);


-- -----------------------------------------------------------------------------
-- Migration 003 — Visibility tiers + friends access + markdown articles
-- Date: 2026-08-02
--
-- Applied automatically at startup by ensure_columns() in app/database.py,
-- which is idempotent. Recorded here for the human-readable history.
-- -----------------------------------------------------------------------------

-- Three-level visibility: 'public' | 'friends' | 'private'
ALTER TABLE habits             ADD COLUMN visibility VARCHAR NOT NULL DEFAULT 'public';
ALTER TABLE articles           ADD COLUMN visibility VARCHAR NOT NULL DEFAULT 'public';
ALTER TABLE projects           ADD COLUMN visibility VARCHAR NOT NULL DEFAULT 'public';
ALTER TABLE portfolio_projects ADD COLUMN visibility VARCHAR NOT NULL DEFAULT 'public';

-- Markdown source for articles. Legacy rows keep their JSON block `body`;
-- body_md takes precedence when non-empty.
ALTER TABLE articles ADD COLUMN body_md TEXT NOT NULL DEFAULT '';

-- A person allowed to see 'friends'-level content. `code` is both the pincode
-- typed on /friend and the ?c= in a share link.
CREATE TABLE IF NOT EXISTS friends (
    id           VARCHAR PRIMARY KEY,
    name         VARCHAR NOT NULL,
    code         VARCHAR NOT NULL UNIQUE,
    created_at   VARCHAR NOT NULL,
    last_seen_at VARCHAR,
    revoked      BOOLEAN NOT NULL DEFAULT FALSE
);


-- -----------------------------------------------------------------------------
-- Migration 004 — Key-file admin login, private calendar, Google sync
-- Date: 2026-08-08
--
-- New tables are created by create_all() at startup; no ALTERs this time, so
-- ensure_columns() has nothing to add. Recorded here for the human history.
--
-- The passcode login is GONE. ADMIN_PASSCODE is no longer read by the app —
-- login now means presenting the contents of bekonai.key (uploaded or pasted).
-- Re-issue with:  python -m app.issue_key > bekonai.key
-- -----------------------------------------------------------------------------

-- Admin credential files. Only the SHA-256 of the secret is stored, so this
-- table is not a copy of the credential. Issuing a new key revokes all others.
CREATE TABLE IF NOT EXISTS admin_keys (
    id           VARCHAR PRIMARY KEY,
    secret_hash  VARCHAR NOT NULL,
    issued_at    VARCHAR NOT NULL,
    revoked      BOOLEAN NOT NULL DEFAULT FALSE,
    last_used_at VARCHAR
);

-- Bektas's private calendar. No `visibility` column on purpose: every route is
-- admin-only, there is no public tier for this data.
-- Times are ISO 8601 strings carrying an explicit Asia/Almaty offset.
CREATE TABLE IF NOT EXISTS calendar_events (
    id               VARCHAR PRIMARY KEY,
    title            VARCHAR NOT NULL,
    starts_at        VARCHAR NOT NULL,
    ends_at          VARCHAR,
    all_day          BOOLEAN NOT NULL DEFAULT FALSE,
    notes            TEXT    NOT NULL DEFAULT '',
    reminder_minutes INTEGER,
    google_event_id  VARCHAR,
    created_at       VARCHAR NOT NULL,
    updated_at       VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_calendar_events_starts_at ON calendar_events (starts_at);

-- Small key/value store for server-side state that is not a domain object:
-- the Google OAuth refresh token, when it was connected, the last sync error.
CREATE TABLE IF NOT EXISTS settings (
    key   VARCHAR PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);


-- -----------------------------------------------------------------------------
-- Migration 005 — Diary (one entry per day, with photos)
-- Date: 2026-08-08
--
-- New tables, created by create_all() at startup. Admin-only at every route,
-- images included — the photo bytes are served through an auth-checked route,
-- never from a public static path.
-- -----------------------------------------------------------------------------

-- One row per day: the day IS the primary key, so writing the same date twice
-- edits that entry instead of creating a second one.
-- Body is markdown (`body_md`), the same format articles use.
CREATE TABLE IF NOT EXISTS diary_entries (
    day        VARCHAR PRIMARY KEY,  -- YYYY-MM-DD, Asia/Almaty
    body_md    TEXT    NOT NULL DEFAULT '',
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL
);

-- Photo metadata only. The bytes live on the Docker volume at
-- /data/uploads/diary — a database that grows by megabytes per photo would
-- make every backup heavier for nothing.
CREATE TABLE IF NOT EXISTS diary_images (
    id           VARCHAR PRIMARY KEY,
    day          VARCHAR NOT NULL REFERENCES diary_entries(day) ON DELETE CASCADE,
    filename     VARCHAR NOT NULL,
    content_type VARCHAR NOT NULL,
    width        INTEGER,
    height       INTEGER,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_diary_images_day ON diary_images (day);


-- -----------------------------------------------------------------------------
-- Migration 006 — Tasks (phase 1 of the tasks/inbox/bot roadmap)
-- Date: 2026-08-08
--
-- New table, created by create_all() at startup. Admin-only, like everything
-- else added since the key-file login.
-- -----------------------------------------------------------------------------

-- due_at holds either a plain 'YYYY-MM-DD' (due that day, no particular time)
-- or a full ISO datetime with the Almaty offset — the same two shapes the
-- calendar uses, so tasks and events can share a day column without conversion.
--
-- `source` is deliberately a free string, not an enum: the telegram and inbox
-- phases will add values ('telegram', 'inbox') and must not need a migration.
CREATE TABLE IF NOT EXISTS tasks (
    id         VARCHAR PRIMARY KEY,
    title      VARCHAR NOT NULL,
    notes      TEXT    NOT NULL DEFAULT '',
    due_at     VARCHAR,
    done       BOOLEAN NOT NULL DEFAULT FALSE,
    done_at    VARCHAR,
    source     VARCHAR NOT NULL DEFAULT 'web',
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tasks_due_at ON tasks (due_at);


-- -----------------------------------------------------------------------------
-- Migration 007 — Quick-capture inbox (phase 2)
-- Date: 2026-08-08
--
-- New tables, created by create_all() at startup. Admin-only, images included.
-- -----------------------------------------------------------------------------

-- A stray thought caught before it is decided about. `triaged_to` records what
-- it became — 'task:<id>' | 'article:<slug>' | 'event:<id>' | 'diary:<day>' |
-- 'dismissed' — as ONE string, so a new triage target costs no migration.
-- `source` follows tasks.source: 'web' now, 'telegram' when the bot lands.
CREATE TABLE IF NOT EXISTS inbox_items (
    id         VARCHAR PRIMARY KEY,
    text       TEXT    NOT NULL DEFAULT '',
    source     VARCHAR NOT NULL DEFAULT 'web',
    triaged_to VARCHAR,
    triaged_at VARCHAR,
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inbox_items_triaged_to ON inbox_items (triaged_to);

-- Photos captured with an item. Bytes on the volume at /data/uploads/inbox.
CREATE TABLE IF NOT EXISTS inbox_images (
    id           VARCHAR PRIMARY KEY,
    item_id      VARCHAR NOT NULL REFERENCES inbox_items(id) ON DELETE CASCADE,
    filename     VARCHAR NOT NULL,
    content_type VARCHAR NOT NULL,
    width        INTEGER,
    height       INTEGER,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inbox_images_item_id ON inbox_images (item_id);


-- -----------------------------------------------------------------------------
-- Migration 008 — Telegram bot reminder idempotency (phase 3)
-- Date: 2026-08-08
--
-- Applied by ensure_columns() at startup: calendar_events already had rows in
-- production, so create_all() would not have touched it.
-- -----------------------------------------------------------------------------

-- Set once the bot has pinged about an event. Without it a restart mid-minute
-- would send the same reminder twice; it is written only AFTER a successful
-- send, so a failed send simply retries on the next tick.
ALTER TABLE calendar_events ADD COLUMN reminder_fired_at VARCHAR;


-- -----------------------------------------------------------------------------
-- Migration 009 — Evening calendar review (event outcomes)
-- Date: 2026-08-08
--
-- New table, created by create_all() at startup — nothing existing is altered,
-- so his live events, tasks and diary are untouched.
-- -----------------------------------------------------------------------------

-- How a planned event actually went. The event id IS the primary key: one
-- answer per event, and answering again overwrites rather than piling up a
-- history — "did I get up at 07:00?" has one true answer per day.
--
-- An event with NO row here was never reviewed; that third state is deliberately
-- absent from `outcome` so an unanswered day scores as unknown, not as zero.
CREATE TABLE IF NOT EXISTS event_outcomes (
    event_id    VARCHAR PRIMARY KEY,
    outcome     VARCHAR NOT NULL,          -- 'done' | 'partial' | 'no'
    note        TEXT,
    recorded_at VARCHAR NOT NULL
);


-- -----------------------------------------------------------------------------
-- Migration 010 — Universal search (SQLite FTS5)
-- Date: 2026-08-09
--
-- Applied by ensure_search_index() at startup (app/services/search_index.py),
-- right after create_all() and ensure_columns(). Idempotent, and SQLite-only.
--
-- ⚠️ This migration is NOT just a CREATE: on first run it BACKFILLS the index
-- from every row that already exists. Without that step his diary, tasks and
-- inbox would only become findable once he happened to edit them again.
-- -----------------------------------------------------------------------------

-- ONE index for all five searchable things rather than one per model. `kind`
-- and `ref` are UNINDEXED (stored, never tokenized) and together form the deep
-- link; `day` is the date the thing is ABOUT, so a hit can be dated without
-- joining back to its source table.
--
-- remove_diacritics 2 folds й→и and ё→е on both sides of the query — he types
-- the word, not the spelling.
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    kind UNINDEXED,
    ref UNINDEXED,
    day UNINDEXED,
    title,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
);

-- Sync is by TRIGGER, not by application code: every write path — web, the
-- Telegram bot, an inbox triage, a future one nobody has written yet — goes
-- through the same three statements, so the index cannot drift because a caller
-- forgot to update it. Three triggers per source table, generated from the
-- SOURCES table in app/services/search_index.py; the update trigger deletes by
-- `old` and inserts from `new` so a renamed writing leaves no ghost row.
--
--   articles       -> kind 'article', ref slug, body = description + body_md
--   diary_entries  -> kind 'diary',   ref day,  body = body_md
--   tasks          -> kind 'task',    ref id,   body = notes
--   calendar_events-> kind 'event',   ref id,   body = notes
--   inbox_items    -> kind 'inbox',   ref id,   body = text (title stays '')
--
-- Shape of each, with `articles` as the example:
--
-- CREATE TRIGGER search_index_article_ai AFTER INSERT ON articles BEGIN
--     INSERT INTO search_index(kind, ref, day, title, body)
--     VALUES ('article', new.slug, new.date, new.title,
--             coalesce(new.description,'') || char(10) || coalesce(new.body_md,''));
-- END;
-- CREATE TRIGGER search_index_article_au AFTER UPDATE ON articles BEGIN
--     DELETE FROM search_index WHERE kind = 'article' AND ref = old.slug;
--     INSERT INTO search_index(...) VALUES (...);   -- as above, from `new`
-- END;
-- CREATE TRIGGER search_index_article_ad AFTER DELETE ON articles BEGIN
--     DELETE FROM search_index WHERE kind = 'article' AND ref = old.slug;
-- END;

-- The backfill, run once when the virtual table is first created:
--
-- INSERT INTO search_index(kind, ref, day, title, body)
-- SELECT 'article', slug, date, title,
--        coalesce(description,'') || char(10) || coalesce(body_md,'')
-- FROM articles;                                    -- and one per source table
--
-- POST /api/search/reindex runs it again from scratch — the escape hatch for a
-- write that bypassed the triggers entirely, such as a restored backup.


-- -----------------------------------------------------------------------------
-- Migration 011 — Hosted portfolio screenshots
-- Date: 2026-08-10
--
-- New table, created by create_all() at startup. No new columns anywhere, so
-- ensure_columns() has nothing to do.
-- -----------------------------------------------------------------------------

-- A screenshot for the projects page, hosted here instead of linked from
-- somewhere else. Deliberately UNBOUND to a project: the add-project form needs
-- a URL before the project row exists, so an upload cannot carry a project id.
-- `portfolio_projects.screenshot_url` merely points at /api/portfolio/images/<id>
-- — an external URL still works and nothing enforces the link.
--
-- Bytes live on the volume at /data/uploads/portfolio (backed up by
-- scripts/backup.sh along with the rest of /data/uploads); only metadata here.
--
-- Serving is PUBLIC — a project card is public content and its <img> has to
-- load for a logged-out reader — while upload and delete stay admin-only.
CREATE TABLE IF NOT EXISTS portfolio_images (
    id           VARCHAR PRIMARY KEY,
    filename     VARCHAR NOT NULL,
    content_type VARCHAR NOT NULL,
    width        INTEGER,
    height       INTEGER,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    created_at   VARCHAR NOT NULL
);


-- -----------------------------------------------------------------------------
-- Migration 012 — Reading list
-- Date: 2026-08-10
--
-- New table, created by create_all() at startup. No new columns on any existing
-- table, so ensure_columns() has nothing to do.
-- -----------------------------------------------------------------------------

-- The public reading list, imported from a Notion database export with
-- `python -m scripts.import_reading <csv>` (idempotent: a title that already
-- exists is skipped, compared case-insensitively and stripped).
--
-- Reads are PUBLIC — the whole point is a page anyone can look at. Create,
-- update and delete are admin-only.
--
-- Everything but the title is nullable: a Notion table is half-filled by
-- nature, and a book that has only been *added* carries nothing but its name.
--
-- `category` is the export's "Type" select, kept a free string so a new one
-- costs no migration (Novel / Self-Development / Spiritual / Programming /
-- Psychology today). `status` is the one closed set:
--     not_started | in_progress | completed | abandoned
-- where `abandoned` is the export's "could not finish" — a shelved book stays
-- part of the reading history rather than being deleted.
--
-- `score` is 1..5 stars or NULL, counted from the ⭐ characters in the export.
-- Dates are ISO 'YYYY-MM-DD'. The export's "Day Count" is NOT stored: it is
-- completed - started, and a derived number that can disagree with its own
-- inputs is worse than none. The client computes it.
CREATE TABLE IF NOT EXISTS reading_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      VARCHAR NOT NULL,
    author     VARCHAR,
    category   VARCHAR,
    status     VARCHAR NOT NULL DEFAULT 'not_started',
    pages      INTEGER,
    score      INTEGER,
    started    VARCHAR,
    completed  VARCHAR,
    created_at VARCHAR NOT NULL
);

-- The list is read newest-finished-first, so the ordering column is indexed.
CREATE INDEX IF NOT EXISTS ix_reading_items_completed ON reading_items (completed);


-- -----------------------------------------------------------------------------
-- Migration 013 — Habit categories
-- Date: 2026-08-10
--
-- A new column on a table that already has rows, so create_all() will NOT add
-- it. Applied automatically at startup by ensure_columns() in app/database.py
-- (entry: habits/category), which is idempotent. Recorded here for the history.
-- -----------------------------------------------------------------------------

-- What a habit is *for* — 'education' / 'health' / 'islam' / … Kept a free
-- string rather than an enum, the same reasoning as reading_items.category and
-- tasks.source: a new grouping must cost no migration.
--
-- Nullable with NO default: every habit already tracked stays ungrouped until
-- Bektas says otherwise, and a blank category from the UI is normalized to
-- NULL on the way in (app/services/habits.py normalize_category) so the list
-- never grows an empty-string group.
ALTER TABLE habits ADD COLUMN category VARCHAR;


-- -----------------------------------------------------------------------------
-- Migration 014 — A habit day can be *partially* done
-- Date: 2026-08-10
--
-- A new column on a table that already has rows, so create_all() will NOT add
-- it. Applied automatically at startup by ensure_columns() in app/database.py
-- (entry: habit_completions/state), which is idempotent. Recorded here for the
-- history.
-- -----------------------------------------------------------------------------

-- The swipe tracker needs a third answer: "I did some of it". That is stored on
-- the completion row rather than as a new table or a new column on habits —
-- it is a fact about one day, and habit_completions already IS the day.
--
-- The domain is exactly two values, 'done' | 'partial'. A missed day is the
-- ABSENCE of a row, as it always has been; there is no 'none' state on disk.
-- Storing one would mean teaching every existing read to filter it out, and
-- those reads (stats, streaks, the assistant's context) all currently spell
-- "not done" as "no row".
--
-- NOT NULL DEFAULT 'done' is the whole backfill: every completion recorded
-- before today was a full tick, so the default states the truth about them.
--
-- Over the API this surfaces in `completed_days` as `true | "partial"` — 'done'
-- is serialized as the boolean it used to be, so a client that only ever
-- truthy-checked the map keeps working without knowing partial exists.
--
-- Deliberately UNCHANGED: habit stats and streaks count any row, so a partial
-- day still keeps a streak alive. A day he did something is nearer to done
-- than to missed, and that is the same call review_score.py already makes
-- (done=1, partial=½, no=0) rather than treating partial as a failure.
ALTER TABLE habit_completions ADD COLUMN state VARCHAR NOT NULL DEFAULT 'done';
-- Migration 015 — Islam section (khatms, prayers, books, audio)
-- Date: 2026-08-10
--
-- Ten new tables, all created by create_all() at startup. No new columns on any
-- existing table, so ensure_columns() has nothing to do.
--
-- EVERYTHING here is admin-only, cover images included. There is no public view
-- of any of it, not even a degraded one — the diary's rule, not the portfolio's.
-- -----------------------------------------------------------------------------

-- Several khatms run at once: one of his own plus whatever shared khatm he has
-- been handed a slice of. `kind` is the one closed set (individual | shared)
-- and `portion` says which slice, as free text — "juz 5", "pages 81-100",
-- "Ya-Sin" are all things a group chat will hand him, and an enum would have to
-- guess the vocabulary.
--
-- There is deliberately NO pages_logged column. It is the sum of the log
-- entries' ranges, computed on read: a stored counter drifts away from the
-- entries that produced it the first time one is deleted, and a number that
-- disagrees with its own inputs is worse than no number (the same reasoning
-- that kept reading_items from storing the export's "Day Count").
--
-- completed_at NULL = still running; the list sorts active khatms first.
CREATE TABLE IF NOT EXISTS quran_khatms (
    id           VARCHAR PRIMARY KEY,
    name         VARCHAR NOT NULL,
    kind         VARCHAR NOT NULL DEFAULT 'individual',
    portion      VARCHAR,
    target_pages INTEGER NOT NULL DEFAULT 604,
    started_at   VARCHAR NOT NULL,
    completed_at VARCHAR
);

-- One sitting. The page range is INCLUSIVE at both ends, so a single page is
-- 41..41 and the pages it accounts for are page_to - page_from + 1. Validated
-- 1 <= page_from <= page_to <= 604 on the way in.
CREATE TABLE IF NOT EXISTS quran_log_entries (
    id        VARCHAR PRIMARY KEY,
    khatm_id  VARCHAR NOT NULL REFERENCES quran_khatms(id) ON DELETE CASCADE,
    date      VARCHAR NOT NULL,
    page_from INTEGER NOT NULL,
    page_to   INTEGER NOT NULL,
    note      TEXT
);

CREATE INDEX IF NOT EXISTS ix_quran_log_entries_khatm_id ON quran_log_entries (khatm_id);
CREATE INDEX IF NOT EXISTS ix_quran_log_entries_date ON quran_log_entries (date);

-- ONE note per surah — the surah number IS the primary key, exactly like
-- diary_entries.day. Writing about al-Baqara again edits that note rather than
-- starting a second one, so the UI needs no create/update decision. 1..114 is
-- enforced by the route (422 outside it), not by a CHECK, so a fixture can not
-- be wedged by a database the app cannot migrate.
CREATE TABLE IF NOT EXISTS sura_notes (
    surah      INTEGER PRIMARY KEY,
    body_md    TEXT    NOT NULL DEFAULT '',
    updated_at VARCHAR NOT NULL
);

-- One cell of the prayer grid. A row exists ONLY where something was actually
-- marked: an untouched day is an absence, not seven NULL rows, and clearing
-- both fields deletes the row again. That is what keeps "not filled in" and
-- "skipped" distinguishable — a boolean grid could not.
--
--   prayer  fajr | dhuhr | asr | maghrib | isha | awwabin | tahajjud
--   status  in_time | late | skipped | qaza_restored   (qaza_restored is a
--           missed prayer made up later — the recovery, worth its own value)
--   quality focus | lazy                (separate from status on purpose: a
--           prayer can be on time and absent-minded)
CREATE TABLE IF NOT EXISTS prayer_marks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    VARCHAR NOT NULL,
    prayer  VARCHAR NOT NULL,
    status  VARCHAR,
    quality VARCHAR,
    CONSTRAINT uq_prayer_date_name UNIQUE (date, prayer)
);

CREATE INDEX IF NOT EXISTS ix_prayer_marks_date ON prayer_marks (date);

-- Books and audio are separate tables rather than one items table with a type
-- column: they diverge where it matters (a book note points at a page range, an
-- audio note at a free-text position; a book session counts pages, an audio
-- session counts minutes) and a shared table would carry both sets of columns
-- half-empty forever.
--
-- cover_image is the FILENAME on the Docker volume (/data/uploads/islam) — not
-- bytes, not a URL — the same split the diary's and the portfolio's photos use.
-- Serving is auth-checked (GET /api/islam/books/covers/{id}); the portfolio's
-- public-image exception does NOT apply here.
--
-- status: reading | finished | shelved, where shelved is "put down, not
-- abandoned" — kept visible rather than deleted.
CREATE TABLE IF NOT EXISTS islam_books (
    id          VARCHAR PRIMARY KEY,
    title       VARCHAR NOT NULL,
    author      VARCHAR,
    description TEXT,
    cover_image VARCHAR,
    status      VARCHAR NOT NULL DEFAULT 'reading',
    total_pages INTEGER,
    created_at  VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS islam_book_notes (
    id        VARCHAR PRIMARY KEY,
    book_id   VARCHAR NOT NULL REFERENCES islam_books(id) ON DELETE CASCADE,
    date      VARCHAR NOT NULL,
    page_from INTEGER,
    page_to   INTEGER,
    body_md   TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_islam_book_notes_book_id ON islam_book_notes (book_id);
CREATE INDEX IF NOT EXISTS ix_islam_book_notes_date ON islam_book_notes (date);

CREATE TABLE IF NOT EXISTS islam_book_sessions (
    id      VARCHAR PRIMARY KEY,
    book_id VARCHAR NOT NULL REFERENCES islam_books(id) ON DELETE CASCADE,
    date    VARCHAR NOT NULL,
    pages   INTEGER NOT NULL DEFAULT 0,
    minutes INTEGER
);

CREATE INDEX IF NOT EXISTS ix_islam_book_sessions_book_id ON islam_book_sessions (book_id);
CREATE INDEX IF NOT EXISTS ix_islam_book_sessions_date ON islam_book_sessions (date);

-- kind: audiobook | playlist — an audiobook has an author reading a text, a
-- playlist is a set of lectures or recitations. Different enough to filter on,
-- not different enough to split into two tables.
CREATE TABLE IF NOT EXISTS islam_audio (
    id          VARCHAR PRIMARY KEY,
    title       VARCHAR NOT NULL,
    creator     VARCHAR,
    description TEXT,
    cover_image VARCHAR,
    kind        VARCHAR NOT NULL DEFAULT 'audiobook',
    status      VARCHAR NOT NULL DEFAULT 'reading',
    created_at  VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS islam_audio_notes (
    id       VARCHAR PRIMARY KEY,
    audio_id VARCHAR NOT NULL REFERENCES islam_audio(id) ON DELETE CASCADE,
    date     VARCHAR NOT NULL,
    position VARCHAR,
    body_md  TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_islam_audio_notes_audio_id ON islam_audio_notes (audio_id);
CREATE INDEX IF NOT EXISTS ix_islam_audio_notes_date ON islam_audio_notes (date);

CREATE TABLE IF NOT EXISTS islam_audio_sessions (
    id       VARCHAR PRIMARY KEY,
    audio_id VARCHAR NOT NULL REFERENCES islam_audio(id) ON DELETE CASCADE,
    date     VARCHAR NOT NULL,
    minutes  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_islam_audio_sessions_audio_id ON islam_audio_sessions (audio_id);
CREATE INDEX IF NOT EXISTS ix_islam_audio_sessions_date ON islam_audio_sessions (date);

-- 2026-08-10 — the public Shelf view of the reading list.
--
-- A blurb and a cover, both on the row that already exists, so both are
-- ALTER TABLE and not just a Mapped[...] attribute (create_all() adds tables,
-- never columns — see _ADDED_COLUMNS in app/database.py).
--
-- cover_image is the FILENAME on the Docker volume (/data/uploads/reading) —
-- not bytes, not a URL. Unlike the Islam shelf, serving it is PUBLIC
-- (GET /api/reading/covers/{id}, Cache-Control: public): /reading is a page
-- anyone can look at, which is the portfolio's exception, not the diary's
-- rule. Upload and delete stay admin-only.
--
-- The cover is deliberately NOT part of the PUT body: that body is a full
-- replace, and a field it does not carry would be cleared on every edit.
ALTER TABLE reading_items ADD COLUMN description TEXT;
ALTER TABLE reading_items ADD COLUMN cover_image VARCHAR;

-- The two logs hanging off a book, both ADMIN-ONLY over the API — unlike the
-- shelf row itself. What he is reading is public; what he wrote about it is
-- not, so neither of these has a public read the way reading_items does.
--
-- Integer ids and an integer FK, matching reading_items. The Islam shelf's
-- notes are VARCHAR because its books are: a log table follows the table it
-- hangs off, not the other section.
CREATE TABLE IF NOT EXISTS reading_notes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL REFERENCES reading_items(id) ON DELETE CASCADE,
    date      VARCHAR NOT NULL,
    page_from INTEGER,
    page_to   INTEGER,
    body_md   TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_reading_notes_item_id ON reading_notes (item_id);
CREATE INDEX IF NOT EXISTS ix_reading_notes_date ON reading_notes (date);

CREATE TABLE IF NOT EXISTS reading_sessions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES reading_items(id) ON DELETE CASCADE,
    date    VARCHAR NOT NULL,
    pages   INTEGER NOT NULL DEFAULT 0,
    minutes INTEGER
);

CREATE INDEX IF NOT EXISTS ix_reading_sessions_item_id ON reading_sessions (item_id);
CREATE INDEX IF NOT EXISTS ix_reading_sessions_date ON reading_sessions (date);

-- 2026-08-11 — sleep tracking.
--
-- The pipeline is Huawei Band 7 → Huawei Health (iOS) → Apple Health → an
-- Apple Shortcuts automation that POSTs the night's samples every morning to
-- POST /api/health/sleep. That POST authenticates with the static
-- HEALTH_INGEST_TOKEN bearer, NOT the admin key file — an unattended iOS
-- automation cannot post a multipart key file, and should not hold a
-- credential that opens the rest of the site. Reading the nights back
-- (GET /api/health/sleep) is admin-only: how he sleeps is as private as the
-- diary.
--
-- The date is the PRIMARY KEY, the same call diary_entries makes: the shortcut
-- may run twice on a bad morning, and the second run has to REPLACE the night
-- rather than grow a second row. The date is the LOCAL (Almaty) date of the
-- last sample's end — a night belongs to the morning you woke up, so
-- 23:00 → 07:00 is filed under the 07:00 day.
--
-- A NULL on a stage column means the band never reported that stage, NOT that
-- it measured zero. Only asleep_minutes is always a number. Minutes are the
-- UNION of their segments, never the sum: Apple Health routinely holds two
-- sources describing the same minutes, and adding them up invents sleep.
--
-- `segments` keeps the raw sample list (start/end/stage/raw_stage) as JSON.
-- Staging is the part of this pipeline most likely to be re-thought, and a
-- re-analysis is only possible if the minutes behind the aggregates were kept.
CREATE TABLE IF NOT EXISTS sleep_nights (
    date           VARCHAR PRIMARY KEY,
    in_bed_minutes INTEGER,
    asleep_minutes INTEGER NOT NULL DEFAULT 0,
    deep_minutes   INTEGER,
    rem_minutes    INTEGER,
    core_minutes   INTEGER,
    awake_minutes  INTEGER,
    bedtime        VARCHAR,
    wake_time      VARCHAR,
    segments       JSON    NOT NULL,
    created_at     VARCHAR NOT NULL,
    updated_at     VARCHAR NOT NULL
);
