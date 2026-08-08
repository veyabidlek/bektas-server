#!/bin/bash
# Daily backup of bektas.app's SQLite database AND the diary photo uploads.
#
# The whole point of choosing SQLite here (2026-08-01) was that the database
# is one file — so a backup is a copy, and a restore is putting it back.
# This exists because the previous storage (a Supabase project) was deleted
# and took every article, portfolio entry and about-section with it.
#
# Uses `sqlite3 .backup`, NOT `cp`: it takes a consistent snapshot even while
# the API is mid-write. Keeps 14 days.
#
# The diary (2026-08-08) keeps photo *metadata* in SQLite but the bytes on the
# volume at /data/uploads, so a database backup alone would restore entries
# pointing at missing pictures. Both halves are captured here.
set -euo pipefail

CONTAINER=bektas-server-app-1
DEST=/home/claude/backups/bektas
KEEP_DAYS=14

mkdir -p "$DEST"
STAMP=$(date +%F_%H-%M-%S)
OUT="$DEST/bektas-$STAMP.db"

# .backup runs inside the container (that is where the volume is mounted),
# then we stream the snapshot out.
docker exec "$CONTAINER" python -c "
import sqlite3
src = sqlite3.connect('/data/bektas.db')
dst = sqlite3.connect('/tmp/backup.db')
src.backup(dst)
dst.close(); src.close()
"
docker cp "$CONTAINER:/tmp/backup.db" "$OUT"
docker exec "$CONTAINER" rm -f /tmp/backup.db
gzip -f "$OUT"

find "$DEST" -name 'bektas-*.db.gz' -mtime +"$KEEP_DAYS" -delete
echo "[bektas-backup] $(basename "$OUT").gz ($(du -h "$OUT.gz" | cut -f1))"

# --- diary photo uploads -----------------------------------------------------
# Tarred from inside the container, where the volume is mounted. Absent on a
# fresh install (nobody has uploaded yet), which is not an error.
UPLOADS_OUT="$DEST/bektas-uploads-$STAMP.tar.gz"

if docker exec "$CONTAINER" test -d /data/uploads; then
    docker exec "$CONTAINER" tar -czf /tmp/uploads.tar.gz -C /data uploads
    docker cp "$CONTAINER:/tmp/uploads.tar.gz" "$UPLOADS_OUT"
    docker exec "$CONTAINER" rm -f /tmp/uploads.tar.gz
    find "$DEST" -name 'bektas-uploads-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
    echo "[bektas-backup] $(basename "$UPLOADS_OUT") ($(du -h "$UPLOADS_OUT" | cut -f1))"
else
    echo "[bektas-backup] no /data/uploads yet — skipping photo backup"
fi
