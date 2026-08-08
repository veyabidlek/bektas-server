"""(Re)issue the admin key file.

    docker compose -f docker-compose.prod.yml exec -T app python -m app.issue_key \
        > bekonai.key && chmod 600 bekonai.key

Writes the key-file JSON to **stdout only** (progress goes to stderr) so the
command above produces a clean file. Every previous key is revoked the moment
this runs — the old bekonai.key stops working immediately.
"""

import json
import sys

import app.models  # noqa: F401  — registers every table before create_all()
from app.database import SessionLocal, create_tables
from app.services import admin_key as svc


def main() -> None:
    create_tables()
    db = SessionLocal()
    try:
        document = svc.issue_key(db)
    finally:
        db.close()

    print(
        f"Issued admin key {document['id']} at {document['issued_at']}. "
        "All previous keys are now revoked.",
        file=sys.stderr,
    )
    json.dump(document, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
