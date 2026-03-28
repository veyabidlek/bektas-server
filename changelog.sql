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
