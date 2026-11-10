# HANDOFF — shared task board

Both agents (CodeGPT and freebuff) read and update this file. One line per task.

Status values: `todo` · `claimed:<agent>` · `done` · `blocked:<reason>`

| # | Task | Status | Owner | Notes |
| - | ---- | ------ | ----- | ----- |
| 1 | Uncommitted working-tree changes in `Shopvpn` (49 entries: `admin_dedicated_sub.py`, `admin_update.py`, `admin_panel/*`, `i18n_extra.py`, …) | `blocked:ownership-unknown` | — | freebuff-authored work in progress? Must be reviewed and committed before anyone else edits those files. |
| 2 | Migrate agent workspace from `E:\codegpt` to `e:\Z\new shop\Shopvpn` | `done` | CodeGPT | Files copied to `E:\Z\_backup_codegpt_workspace`; CodeGPT workspace key in its DB now points only at this repo. |
| 3 | Add an on/off switch for the reseller (نمایندگی) section in the Telegram admin panel | `done` | freebuff | Toggle lives in admin → نمایندگی‌ها; hides user-facing reseller buttons and blocks their handlers when off. Changes are in the working tree (not committed). Tests: 132 passed, ruff/i18n clean. |

## Rules

- Claim a row (`claimed:codegpt` / `claimed:freebuff`) **before** editing files.
- If you finish, set `done` and add the commit SHA in Notes.
- If you touch files another agent has claimed, stop and coordinate via this file.
- Never leave a row `claimed:` for more than one working session without a note.
