I want you to review the GitHub PR $repo_full_name#$pr_number.

Here is the PR title and description : 

Title: `$pr_title`

Description:

`$pr_description`

The repo is cloned at `$working_dir`. The working tree holds the PR's
content as if uncommitted on top of the base — inspect it with
`git diff` or `git status` (no extra args needed). The PR's own commits
stay reachable as the `$pr_ref` ref and at SHA `$head_sha`
(base: `$base_sha`), so `git log $pr_ref` or `git log $head_sha`
shows the commit history if you want it.

A scratchpad lives at `$memory_file` in the repo root (git-ignored,
not part of the PR). It already records the PR coordinates and SHAs,
and you can append your own notes there to carry context across
exploration steps.

Read surrounding code with your `read_file` / `grep` tools when context
is missing. If `$agents_md` exists at the repo root, treat its
conventions as authoritative.

Output one markdown report in the chat covering: correctness bugs, security issues,
and clarity problems. Skip nits and style preferences. Be concise —
focus on the highest-signal findings, not exhaustive coverage. 
Always write the report in the language of the description of the PR, default english if no description nor title.
your last message should only contain the markdown report.
