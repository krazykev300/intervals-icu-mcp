# AGENTS.md

Every coding agent working in this repository (Cursor, Codex, Claude, and
others) follows [CLAUDE.md](CLAUDE.md). Read it in full before making changes.
It is the single source of instructions; this file only points to it, so the
two cannot drift apart.

The sections that matter most when more than one agent is working:

- **Working across Claude and Cursor**: backlog lanes, `**Done:**` markers,
  one writer per set of files, one PR per lane.
- **Testing**: doc counts and playbook wording are checked by tests; run
  `make smoke` before merging a change to a write tool.
- **Verification**: run `make can-release` before finishing.
- **Merging PRs** and **Releases**: squash-merge only, conventional PR
  titles, and a CHANGELOG bullet in the same PR.
