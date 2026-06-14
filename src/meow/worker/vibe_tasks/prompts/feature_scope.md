I want you to scope a feature request filed as the GitHub issue
$repo_full_name#$issue_number — assess how it could be implemented and what
stands in the way. This is a FEASIBILITY and SCOPING analysis: do NOT write
any code, do NOT create commits or branches, do NOT modify any file in the
repo. Read and reason only.

Here is the issue title and description:

Title: `$issue_title`

Description:

`$issue_body`

The repository is cloned at `$working_dir` on its default branch
(`$default_branch`) — a clean checkout, no pending changes. Explore it with
your `read_file` / `grep` tools (and `git log` if history helps) to ground
your analysis in the real code: entry points, the components the feature
would touch, existing patterns to reuse, and integration points.

If `$agents_md` exists at the repo root, treat its conventions as
authoritative for how the feature should fit the codebase.

Write your scoping report as one markdown document to the file `$report_file`
using your `write_file` tool, in a single call. The report should cover:

1. **Feasibility** — overall verdict and the reasoning behind it.
2. **Approach** — how the feature could be implemented, high level.
3. **Components to touch** — the concrete files/modules involved (cite real
   paths you found).
4. **Blocking points & risks** — architectural constraints, missing
   prerequisites, ambiguities in the request that need a decision.
5. **Effort estimate** — a rough T-shirt size (S / M / L / XL) with a one-line
   justification.

Be concise and high-signal — this is a map for whoever implements it, not an
exhaustive spec. Write the report in the language of the issue (default
English if neither title nor description gives one).

`$report_file` is the ONLY deliverable: write the complete report there. Do
NOT print the report in the chat — chat output is discarded and never seen.
Writing the file is the last thing you do.
