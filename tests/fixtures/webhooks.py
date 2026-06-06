"""Reusable webhook payload builders for tests.

These builders return JSON-encodable dicts that satisfy githubkit's strict
Pydantic webhook models. They are deliberately verbose: every field that
``WebhookIssueCommentCreated`` and friends require is set, so the fixtures
can be re-parsed via ``githubkit.webhooks.parse_obj`` without surprises.
"""

from __future__ import annotations

import json
from typing import Any


def _simple_user(login: str, user_id: int = 1) -> dict[str, Any]:
    return {
        "login": login,
        "id": user_id,
        "node_id": "U_kgDOABCDEF",
        "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
        "gravatar_id": "",
        "url": f"https://api.github.com/users/{login}",
        "html_url": f"https://github.com/{login}",
        "followers_url": f"https://api.github.com/users/{login}/followers",
        "following_url": f"https://api.github.com/users/{login}/following{{/other_user}}",
        "gists_url": f"https://api.github.com/users/{login}/gists{{/gist_id}}",
        "starred_url": f"https://api.github.com/users/{login}/starred{{/owner}}{{/repo}}",
        "subscriptions_url": f"https://api.github.com/users/{login}/subscriptions",
        "organizations_url": f"https://api.github.com/users/{login}/orgs",
        "repos_url": f"https://api.github.com/users/{login}/repos",
        "events_url": f"https://api.github.com/users/{login}/events{{/privacy}}",
        "received_events_url": f"https://api.github.com/users/{login}/received_events",
        "type": "User",
        "site_admin": False,
    }


def _reactions() -> dict[str, Any]:
    return {
        "+1": 0,
        "-1": 0,
        "confused": 0,
        "eyes": 0,
        "heart": 0,
        "hooray": 0,
        "laugh": 0,
        "rocket": 0,
        "total_count": 0,
        "url": "https://api.github.com/reactions",
    }


def _pull_request_link() -> dict[str, Any]:
    return {
        "url": "https://api.github.com/repos/octocat/hello/pulls/1",
        "html_url": "https://github.com/octocat/hello/pull/1",
        "diff_url": "https://github.com/octocat/hello/pull/1.diff",
        "patch_url": "https://github.com/octocat/hello/pull/1.patch",
        "merged_at": None,
    }


def issue_comment_payload(
    *,
    sender_login: str = "alice",
    action: str = "created",
    body: str = "hello",
    is_pr: bool = False,
) -> dict[str, Any]:
    """Build an issue_comment webhook payload as a Python dict.

    Set ``is_pr=True`` to include the ``issue.pull_request`` link that GitHub
    sends when the underlying issue is actually a PR — this is what
    ``detect_intent`` checks to gate on PRs.
    """

    sender = _simple_user(sender_login, user_id=42)
    owner = _simple_user("octocat", user_id=2)
    issue_user = {"id": 42, "login": sender_login}
    comment_user = {"id": 42, "login": sender_login}
    issue: dict[str, Any] = {
        "active_lock_reason": None,
        "assignee": None,
        "assignees": [],
        "author_association": "NONE",
        "body": None,
        "closed_at": None,
        "comments": 0,
        "comments_url": "https://api.github.com/repos/octocat/hello/issues/1/comments",
        "created_at": "2024-01-01T00:00:00Z",
        "events_url": "https://api.github.com/repos/octocat/hello/issues/1/events",
        "html_url": "https://github.com/octocat/hello/issues/1",
        "id": 100,
        "labels": [],
        "labels_url": "https://api.github.com/repos/octocat/hello/issues/1/labels{/name}",
        "locked": False,
        "milestone": None,
        "node_id": "I_kwDOABCD",
        "number": 1,
        "reactions": _reactions(),
        "repository_url": "https://api.github.com/repos/octocat/hello",
        "state": "open",
        "title": "An issue",
        "updated_at": "2024-01-01T00:00:00Z",
        "url": "https://api.github.com/repos/octocat/hello/issues/1",
        "user": issue_user,
    }
    if is_pr:
        issue["pull_request"] = _pull_request_link()

    return {
        "action": action,
        "installation": {
            "id": 99,
            "node_id": "MDIzOkludGVncmF0aW9uSW5zdGFsbGF0aW9uOTk=",
        },
        "comment": {
            "author_association": "NONE",
            "body": body,
            "created_at": "2024-01-01T00:00:00Z",
            "html_url": "https://github.com/octocat/hello/issues/1#issuecomment-1",
            "id": 1,
            "issue_url": "https://api.github.com/repos/octocat/hello/issues/1",
            "node_id": "IC_kwDOABCD",
            "performed_via_github_app": None,
            "reactions": _reactions(),
            "updated_at": "2024-01-01T00:00:00Z",
            "url": "https://api.github.com/repos/octocat/hello/issues/comments/1",
            "user": comment_user,
        },
        "issue": issue,
        "repository": {
            "id": 10,
            "node_id": "R_kgDOABCD",
            "name": "hello",
            "full_name": "octocat/hello",
            "license": None,
            "forks": 0,
            "owner": owner,
            "private": False,
            "html_url": "https://github.com/octocat/hello",
            "description": None,
            "fork": False,
            "url": "https://api.github.com/repos/octocat/hello",
            "archive_url": "https://api.github.com/repos/octocat/hello/{archive_format}{/ref}",
            "assignees_url": "https://api.github.com/repos/octocat/hello/assignees{/user}",
            "blobs_url": "https://api.github.com/repos/octocat/hello/git/blobs{/sha}",
            "branches_url": "https://api.github.com/repos/octocat/hello/branches{/branch}",
            "collaborators_url": "https://api.github.com/repos/octocat/hello/collaborators{/collaborator}",
            "comments_url": "https://api.github.com/repos/octocat/hello/comments{/number}",
            "commits_url": "https://api.github.com/repos/octocat/hello/commits{/sha}",
            "compare_url": "https://api.github.com/repos/octocat/hello/compare/{base}...{head}",
            "contents_url": "https://api.github.com/repos/octocat/hello/contents/{+path}",
            "contributors_url": "https://api.github.com/repos/octocat/hello/contributors",
            "deployments_url": "https://api.github.com/repos/octocat/hello/deployments",
            "downloads_url": "https://api.github.com/repos/octocat/hello/downloads",
            "events_url": "https://api.github.com/repos/octocat/hello/events",
            "forks_url": "https://api.github.com/repos/octocat/hello/forks",
            "git_commits_url": "https://api.github.com/repos/octocat/hello/git/commits{/sha}",
            "git_refs_url": "https://api.github.com/repos/octocat/hello/git/refs{/sha}",
            "git_tags_url": "https://api.github.com/repos/octocat/hello/git/tags{/sha}",
            "git_url": "git://github.com/octocat/hello.git",
            "issue_comment_url": "https://api.github.com/repos/octocat/hello/issues/comments{/number}",
            "issue_events_url": "https://api.github.com/repos/octocat/hello/issues/events{/number}",
            "issues_url": "https://api.github.com/repos/octocat/hello/issues{/number}",
            "keys_url": "https://api.github.com/repos/octocat/hello/keys{/key_id}",
            "labels_url": "https://api.github.com/repos/octocat/hello/labels{/name}",
            "languages_url": "https://api.github.com/repos/octocat/hello/languages",
            "merges_url": "https://api.github.com/repos/octocat/hello/merges",
            "milestones_url": "https://api.github.com/repos/octocat/hello/milestones{/number}",
            "notifications_url": "https://api.github.com/repos/octocat/hello/notifications{?since,all,participating}",
            "pulls_url": "https://api.github.com/repos/octocat/hello/pulls{/number}",
            "releases_url": "https://api.github.com/repos/octocat/hello/releases{/id}",
            "ssh_url": "git@github.com:octocat/hello.git",
            "stargazers_url": "https://api.github.com/repos/octocat/hello/stargazers",
            "statuses_url": "https://api.github.com/repos/octocat/hello/statuses/{sha}",
            "subscribers_url": "https://api.github.com/repos/octocat/hello/subscribers",
            "subscription_url": "https://api.github.com/repos/octocat/hello/subscription",
            "tags_url": "https://api.github.com/repos/octocat/hello/tags",
            "teams_url": "https://api.github.com/repos/octocat/hello/teams",
            "trees_url": "https://api.github.com/repos/octocat/hello/git/trees{/sha}",
            "clone_url": "https://github.com/octocat/hello.git",
            "mirror_url": None,
            "hooks_url": "https://api.github.com/repos/octocat/hello/hooks",
            "svn_url": "https://github.com/octocat/hello",
            "homepage": None,
            "language": None,
            "forks_count": 0,
            "stargazers_count": 0,
            "watchers_count": 0,
            "size": 0,
            "default_branch": "main",
            "open_issues_count": 0,
            "has_issues": True,
            "has_projects": True,
            "has_wiki": True,
            "has_pages": False,
            "has_downloads": True,
            "archived": False,
            "disabled": False,
            "pushed_at": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "open_issues": 0,
            "watchers": 0,
        },
        "sender": sender,
    }


def issue_comment_body(**kwargs: Any) -> bytes:
    """Same payload, JSON-encoded for the receiver tests."""

    return json.dumps(issue_comment_payload(**kwargs)).encode("utf-8")
