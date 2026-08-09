"""The Sunday digest: the week behind, the thread through it, the week ahead.

Assembly only. The counting is `app/services/weekly.py` + `week_stats.py`, the
wording is `copy.weekly_digest`, and the paragraph is `weekly_summary.py` —
which returns None whenever the model is unconfigured, slow or broken, so the
digest is never blocked by it.

Unlike the evening review, this always sends. A week with nothing recorded is
still a week worth closing, and the message says so in one line.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.bot import copy
from app.bot.client import TelegramClient
from app.services import weekly as weekly_svc
from app.services import weekly_summary
from app.services.calendar import ASTANA
from app.services.week_stats import week_containing

log = logging.getLogger("bot.weekly")


def build_message(db: Session, now: datetime | None = None, *, with_summary: bool = True) -> str:
    """The whole message, for a Sunday or for `/digest` on any other day.

    The week is always the Monday-based one *containing* `now` — on a Sunday
    evening that is the week just finished, which is what the digest is for.
    """
    week = week_containing(now or datetime.now(ASTANA))

    stats = weekly_svc.stats_for(db, week)
    ahead = weekly_svc.ahead(db, week)

    summary = None
    if with_summary:
        # Worst case this blocks the poll loop for the LLM timeout, once a
        # week. Cheaper than a thread, and reminders are a minute-granular
        # feature that tolerates it.
        summary = weekly_summary.summarize(stats, weekly_svc.content_for(db, week))
        if summary is None:
            log.info("weekly digest going out without a summary")

    return copy.weekly_digest(stats, ahead, summary)


def send_weekly(
    db: Session, tg: TelegramClient, chat_id: int, now: datetime | None = None
) -> None:
    tg.send_message(chat_id, build_message(db, now))
