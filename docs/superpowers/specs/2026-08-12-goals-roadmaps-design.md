# Goals — neetcode.io-style roadmaps

**Status:** design, decided autonomously. Bektas asked for this and went to
sleep with "do urself", so every open question below was decided by me. Each
decision records its reasoning so any of them can be overruled cheaply.

## What he asked for

> add in bektas.app goals section where i can create roadmaps like in
> neetcode.io where i make trees and when click on it i can put subtasks with
> to dos and deadlines, do proper ui ux also connect it to ai architecture,
> and when i click on subtask a text opens which is description, it kinda be
> easily edited

## Shape of the thing

Three nouns, one nesting each:

```
Goal (a roadmap)          "Become a strong backend engineer"
└── Node (a tree box)     "Databases"  →  "Indexes"  →  "Query planning"
    └── Task              "Read the Postgres index chapter"  ☑ due 2026-08-20
        └── description   markdown, click to edit
```

- **Goal** — title, optional description, archived flag.
- **Node** — the box drawn in the tree. `parent_id` (null = root), `title`,
  `description` (markdown), `position` among siblings.
- **Task** — the subtask inside a node: `title`, `done`, `due_at`,
  `description` (markdown), `position`.

### Decision: a tree, not a graph

neetcode.io is really a DAG — a few nodes have two parents. A strict tree
(`parent_id`) is one column, needs no edge table, and can be **laid out
automatically**, which in turn means no x/y to store, no dragging to build, and
a roadmap that survives being edited on a phone. He said "trees".

If cross-links ever matter, they arrive as an `edges` table later without
touching what is built here.

### Decision: auto-layout, no free positioning

Positions are derived at render from the tree, not stored. A stored layout is a
second source of truth that goes stale the moment a node is added, and it is
the part of a canvas UI that is worst on a phone.

### Decision: `due_at` lives on the Task, not the Node

It matches what he asked for ("subtasks with to dos and deadlines") and it
matches the existing `tasks` table's format exactly — either `YYYY-MM-DD` or a
full ISO datetime with the Almaty offset — so the two can share a day column
later without translation.

### Decision: progress is derived, never stored

A node is *complete* when it has tasks and all of them are done. A goal's
percentage is done-tasks over total-tasks. Nothing to keep in sync, and the
number the assistant reads is the number the page shows.

## Data model

Three tables, following `app/models/habit.py` conventions (string ids, ISO
string timestamps, `created_at` / `updated_at`).

```
goals         id, title, description, archived, created_at, updated_at
goal_nodes    id, goal_id→goals, parent_id→goal_nodes|null, title,
              description, position, created_at, updated_at
goal_tasks    id, node_id→goal_nodes, title, description, done, done_at,
              due_at, position, created_at, updated_at
```

Deleting a goal deletes its nodes and their tasks; deleting a node deletes its
subtree. Done in the service with an explicit recursive walk rather than
database cascades, because the app's other deletes are explicit too and SQLite
foreign keys are not enforced by default.

**New tables, so `create_all()` handles them** — no `_ADDED_COLUMNS` entry is
needed. `changelog.sql` gets the block regardless (the convention is that the
file is the readable history, not just the migration list).

## API

`/api/goals`, admin-only — same reasoning as tasks and the assistant: this is
his private planning.

| | |
|---|---|
| `GET /api/goals` | list, `include_archived` |
| `POST /api/goals` | create |
| `GET /api/goals/{id}` | one goal with its whole tree + tasks |
| `PATCH /api/goals/{id}` · `DELETE` | edit / delete |
| `POST /api/goals/{id}/nodes` | add a node (`parent_id` optional) |
| `PATCH /api/goals/nodes/{id}` · `DELETE` | edit / delete a node + subtree |
| `POST /api/goals/nodes/{id}/tasks` | add a task |
| `PATCH /api/goals/tasks/{id}` · `DELETE` | edit / delete |
| `POST /api/goals/tasks/{id}/toggle` | flip done, stamps `done_at` |
| `POST /api/goals/ai/draft` | **AI:** goal sentence → a draft tree |
| `POST /api/goals/nodes/{id}/ai/tasks` | **AI:** node → suggested tasks |

`GET /api/goals/{id}` returns the tree already nested, so the client renders
without assembling anything.

## The AI connection

Three touchpoints, all through the existing `app/services/llm.py`, which
**never raises and returns `None`** on any failure. Both generating endpoints
turn `None` into a **503 that says why**, exactly like `/api/assistant/chat`.
Nothing here is required for the feature to work by hand.

1. **Draft a roadmap.** "Become a strong backend engineer" → a tree of 5–8
   top-level areas, each with 2–4 children, each with a one-line description.
   The model returns JSON; `goals_ai.py` parses and validates it *as a pure
   function* (testable without a database or a network), and the service
   writes it. An unparseable answer is a 503, never a half-built goal.
2. **Break a node into tasks.** Same shape, one level, returns task titles with
   optional descriptions. He reviews before they are saved.
3. **The assistant learns about goals.** `build_context(db)` grows an ACTIVE
   GOALS section: each unarchived goal, its percentage, and its nearest
   deadline. This is the documented bargain in the server's CLAUDE.md — *a
   claim the assistant should be able to make needs the number behind it in
   the context first* — so `/a` can say "you have not touched Databases in
   three weeks" instead of guessing.

**Decision: the model drafts, it never silently writes.** Generated trees and
tasks are shown for confirmation first. An assistant that can quietly restructure
a plan is one bad completion away from destroying it.

## UI

`/bekonai-admin/goals`, a new sidebar row (🎯 Goals) under Assistant — it is a
planning tool, so it sits with Calendar and Tasks. English, per the app's
convention for admin surfaces.

- **Index** — a card per goal: title, progress bar, task counts, next deadline.
- **One goal** — the tree, centred, root at the top, children fanning below,
  connectors drawn as SVG behind the boxes. Each box shows its title and a
  small `3/7` counter, and is tinted by progress (empty → outline, partial →
  half-tinted, complete → solid). This is the neetcode read-at-a-glance quality:
  the shape of what is left is visible without opening anything.
- **Node panel** — opens on click, as a right-hand drawer on desktop and a
  bottom sheet on phones (the app already uses this split). Holds the node's
  description and its task list: checkbox, title, due chip, and a disclosure
  that expands the task's description into an editable markdown area.
- **Editing is click-to-edit**, not a modal with a Save button — click the
  text, it becomes a textarea, blur saves. He asked for "easily edited", and a
  modal per description would be four clicks to fix a typo.
- **Rendering markdown** goes through the app's existing `<Markdown>`
  component. ⚠️ It injects `.prose-bektas`, so the drawer must not fight it
  with its own typography.

Mobile is not an afterthought: the tree scrolls horizontally within its own
container, and a node's tap target is the whole box.

## Testing

- **Pure, no database** (`node --test` on the client, pytest on the server):
  the layout maths (tree → x/y + connector paths), progress arithmetic, and
  the AI JSON parser including malformed input.
- **Service level:** create/delete a node deletes its subtree; toggling a task
  stamps and clears `done_at`; a goal's tree comes back nested and ordered.
- The AI endpoints are tested with the model stubbed — no test may depend on
  DeepSeek being reachable.

## Deliberately not in v1

Cross-links between branches (the DAG case), drag-to-reorder, templates or
sharing a roadmap publicly, per-node deadlines, reminders through the bot.
Each is additive; none is needed to answer what he asked for.
