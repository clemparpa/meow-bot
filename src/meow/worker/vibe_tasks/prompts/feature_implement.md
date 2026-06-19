I want you to implement the feature requested in the GitHub issue
$repo_full_name#$issue_number — write the actual code that resolves it.

Here is the issue title and description:

Title: `$issue_title`

Description:

`$issue_body`

The repository is cloned at `$working_dir`, checked out on its default branch
(`$default_branch`). Make your changes directly in this working tree:

- Explore first with `read_file` / `grep` to understand the existing code,
  entry points, patterns, and tests before changing anything.
- Edit code with `search_replace` (preferred for targeted edits) and
  `write_file` (for new files or full rewrites).
- If `$agents_md` exists at the repo root, treat its conventions as
  authoritative — match the project's style, structure, and tooling.
- Run the project's tests / linters / type-checks with `bash` if you can find
  them, and fix what your change breaks. Keep the change focused on this issue;
  do not refactor unrelated code.

IMPORTANT — do NOT run any git or `gh` command (no `add`, `commit`, `branch`,
`checkout`, `push`, …). You have read-only git access and it would fail anyway.
The system reads your working-tree edits, commits them, and opens the pull
request for you. Just leave your changes in the working tree.

When you are done, write the **pull request description** as one markdown
document to the file `$report_file` using your `write_file` tool, in a single
call. It should cover:

1. **Summary** — what the change does and how it resolves the issue.
2. **Changes** — the key files/modules you touched and why.
3. **Testing** — what you ran (tests, lint, type-check) and the result, or why
   you couldn't.
4. **Notes** — anything the reviewer should know: trade-offs, follow-ups, open
   questions.

Be concise and high-signal. Write it in the language of the issue (default
English if neither title nor description gives one).

`$report_file` is the ONLY text deliverable: write the complete PR description
there. Do NOT print it in the chat — chat output is discarded and never seen.
If you determine the feature cannot or should not be implemented, make no code
changes and explain why in `$report_file` instead. Writing the file is the last
thing you do.
