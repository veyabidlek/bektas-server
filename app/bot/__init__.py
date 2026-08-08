"""Bektas's personal Telegram bot.

Runs as a sibling container to the API (same image, `python -m app.bot`), so a
bot crash cannot take the website down. Long polling — one user, one replica,
no inbound port needed.
"""
