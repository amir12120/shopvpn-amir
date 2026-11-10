# AGENTS.md — workspace contract

This file is the shared contract for every AI agent working in this repository
(CodeGPT / Codebuff / freebuff / any other). Read it before touching anything.

## Workspace root

All work happens inside **`e:\Z\new shop\Shopvpn`** (this repository, `amir12120/shopvpn-amir`).
The previous scratch workspace `E:\codegpt` is retired; its contents were copied to
`E:\Z\_backup_codegpt_workspace` and must not be used as a working directory.

Sibling projects live under `E:\Z\new shop\` and are **separate git repos** —
they are not part of this workspace and must not be edited from here:

| Path | Repo | Purpose |
| --- | --- | --- |
| `E:\Z\new shop\AmirHesab` | `amir12120/Warehouse` | desktop Python app (warehouse/accounting) |
| `E:\Z\new shop\gft-TUNNEL` | `amir12120/gft-TUNNEL` | GRE/frp tunnel installer |
| `E:\Z\new shop\TEMp` | `amir12120/TEMp` | static pages site |
| `E:\Z\new shop\.freebuff` | — | freebuff runtime state (do not edit) |

## Coordination between agents

- `HANDOFF.md` in this directory is the shared task board. Claim a task before
  starting it and move it when it is done. Never edit a file another agent has
  claimed unless the claim is released.
- `E:\Z\new shop\AGENTS.md` holds the GitHub authentication rules for the whole
  `E:\Z` tree — follow them as-is (token in `E:\Z\token.txt`, never echoed;
  `.freebuff/gh-token` is revoked and must stay untouched; never ask the user
  for credentials).

## Ground rules

- Smallest possible change that fully solves the request. No drive-by rewrites.
- One logical change per commit; conventional commit subjects.
- `git fetch` and compare with `origin/main` before any push.
- History rewriting (filter-branch / force-push) is never implied by a request
  to push, tag or release — it needs an explicit instruction.
- Commit trailers: no `Co-Authored-By` / `Generated with` lines are added by
  agents in this repo.
- Never print secrets from `.env*`, `token.txt`, git remotes or the CodeGPT DB.

## Project layout (this repo)

Python Telegram-bot VPN shop: `main.py` (entry), `handlers_user.py` /
`handlers_admin.py` (large), `admin_panel/` (FastAPI web UI), `api/`, `db/`,
`miniapp/`, `panel_providers/`, `sub_server/`, `web_store/`, `tests/`.
`requirements.txt` pins runtime deps; config is env-var based (see `.env.example`).
