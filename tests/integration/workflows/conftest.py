"""Mistral Workflows test fixtures for the workflow integration tests.

Pulls the SDK-provided autouse fixtures (`setup_test_config`,
`clear_dependency_cache`, `mock_upsert_search_attributes`) plus the
`temporal_env` fixture into scope for every test under this directory.
The wildcard import is the documented entrypoint — see
`mistralai/workflows/testing/fixtures.py`.
"""

from mistralai.workflows.testing.fixtures import *  # noqa: F401, F403
