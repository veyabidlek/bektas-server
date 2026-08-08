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
