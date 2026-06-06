"""Pytest bootstrap shared by every test in the suite.

Three Settings() instances live at module-level in the receiver
(app.py, client.py, controllers/issue_comment.py) and crash on import
when required env vars are missing. We assign them here, before pytest
collects any test that imports `meow.receiver.*`.

Forced assignment (not `setdefault`) makes the suite deterministic
across machines — a developer's shell-exported MEOW_BOT_LOGIN won't
break the prediction patterns relied upon by integration tests.
Tests that need to vary these values (see test_config.py) use
`monkeypatch.setenv` / `delenv`, which still wins per-test.
"""

from __future__ import annotations

import os

TEST_WEBHOOK_SECRET = "test-secret"
TEST_BOT_LOGIN = "meow-bot"

os.environ["MEOW_DOMAIN"] = "test.example.com"
os.environ["GITHUB_APP_ID"] = "1"
os.environ["GITHUB_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
os.environ["MISTRAL_API_KEY"] = "test-mistral-key"
os.environ["KOYEB_API_TOKEN"] = "test-koyeb-token"
os.environ["DEPLOYMENT_NAME"] = "test-deployment"
os.environ["MEOW_BOT_LOGIN"] = TEST_BOT_LOGIN
