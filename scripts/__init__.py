"""Runnable maintenance scripts.

A package so each one can be started as `python -m scripts.<name>` from the
repository root — inside the app container that puts `app` on the path without
any sys.path juggling, and it lets the tests import the pure helpers.
"""
