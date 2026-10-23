# AI Token Widget

Windows desktop widget showing the remaining context/quota of local AI coding
sessions (Claude Code, Codex, OpenCode) and which of them are running.

**Status: v0.6.0 — project organization, modified-file size and management
load.** All three adapters are wired into the app; refreshes run off the GUI thread, a second
launch reveals the existing window, and quota/state transitions produce
deduplicated tray alerts. Cards are grouped by provider, groups collapse, and
the list can be filtered by activity or searched by project/model. The footer
distinguishes current, slow, stale and failed refreshes. Tray alerts can play an
optional Windows sound, and the last 50 are kept in a local history dialog. The
frameless window can stay always-on-top, use a configurable opacity, start
collapsed and reset its position from Settings. The widget is built as a
PyInstaller onedir application with a separate console binary for the opt-in
Claude Code bridge, plus an Inno Setup installer. A scrollable settings panel
applies notification, threshold, refresh, sound, appearance and per-provider
mute changes without editing JSON, and exposes sanitized diagnostics and log
shortcuts. Claude Code quota is available through that opt-in bridge; until it
is installed, Claude cards show usage and estimated context but no quota.

v0.6.0 adds a project section above the provider groups: sessions are grouped by
working directory, the top six projects are ordered by total tokens, and each
row shows the agents involved, unique modified files, their current on-disk size
and a 1–5 management-load index. Only paths reported by write/edit tool calls are
measured, and file contents are never opened. Prompt text is never retained:
the load index uses prompt frequency and total prompt character count as an
amplitude signal.

## What it shows

- One card per recent session: agent, project, model, running/waiting state,
  context remaining, cumulative tokens, cost where available, and exact quota
  where the provider exposes it.
- Cards grouped by provider in priority order. Each group header shows session,
  running and flagged counts; click it (or press Enter/Space) to collapse it.
  Collapsed groups are remembered between launches.
- A filter bar with `All`, `Running` and `Issues`, plus a search box matching
  project, model and agent name. Filters are session-only and reset on launch.
- A frameless window with a tray icon, drag, collapse and hide-to-tray.
  Always-on-top, opacity and the collapsed start state are configurable.
- Background refresh: transcript and database reads never block the window;
  a failed poll keeps the previous snapshot and reports the error in the footer.
  The footer also shows the snapshot age, `refreshing…`, `refresh slow` after
  15 seconds and `stale` when the last successful update is too old.
- One running instance per user: launching the widget again brings the existing
  window to the front instead of starting a duplicate.
- Tray notifications, only when a condition starts: quota low or exhausted,
  rate-limited/error sessions, and adapter failures. Conditions that already
  exist at startup are not re-announced. An optional Windows sound plays once
  per poll, and the tray menu opens a local history of the last 50 alerts.
- Context and quota bars are green above 50% remaining, amber from 20–50%,
  and red below 20%.
- Estimated values are labelled `(est.)`; quota snapshots show `as of …` when
  they are more than two minutes old.
- A `PROJECTS` section above the provider groups organizes sessions by working
  directory and shows the top six projects by token total. Each row lists the
  agents, session count, unique modified files, current on-disk size and a
  1–5 management-load badge.
- Modified-file totals include only files an agent wrote or edited through a
  write/edit tool call. Paths are normalized and deduplicated before a single
  `os.stat` per file; reads, searches, folder scans and build artifacts are not
  counted. Deleted or unreadable files are counted as missing without bytes.
- The management-load index is a visual heuristic, not a billing or quota
  metric. It combines prompt frequency and average prompt size, current context
  pressure, API-turn frequency and the model class (reasoning, multimodal or
  general).

## Safety invariants

- Agent stores are read-only. SQLite is opened with `mode=ro` and
  `PRAGMA query_only=1`; transcript files are only read.
- The widget never reads `.env`, `.credentials.json`, `auth.json`, or the
  OpenCode `account` / `credential` tables.
- Modified-file paths come from write/edit tool metadata. The widget never opens
  those files: it only calls `os.stat` on the normalized, deduplicated paths.
  File contents, diffs and build artifacts are not read or stored.
- Prompt amplitude is stored as a character count only. Prompt text is never
  retained, logged, shown in notifications or included in diagnostics.
- The Claude bridge persists only rate-limit numbers, reset times and a session
  id. It never stores prompts, transcript paths, cwd, model output or secrets.
- Installing the Claude bridge changes only the `statusLine` field in
  `~/.claude/settings.json`. The undo record stores only the previous
  `statusLine` value, not a copy of the whole settings file (which may contain
  secrets).
- Notifications contain only the agent, project, model, quota label/percentage,
  reset time, adapter error type and timestamp. They never include prompts or
  transcript content.
- `%APPDATA%\AITokenWidget\widget.log` records lifecycle events and exception
  tracebacks for troubleshooting; it does not log transcript contents or
  credential values.
- The diagnostics report copied from Settings contains counts, timings, settings
  and adapter error labels only. It never includes prompts, transcript text,
  session ids, project paths, cwd or credentials.
- `%APPDATA%\AITokenWidget\notifications.json` stores only the alert timestamp,
  title and message, which are the same fields shown in the tray. It does not
  store alert keys, session ids, prompts or transcript text.
- No changes outside `ai_token_widget/`; `telegram_bots/` is untouched.

## Usage

```powershell
# one-time setup
python -m venv ai_token_widget\.venv
ai_token_widget\.venv\Scripts\python.exe -m pip install -r ai_token_widget\requirements.txt

# run the widget
ai_token_widget\.venv\Scripts\python.exe -m ai_token_widget

# tests (headless Qt)
$env:QT_QPA_PLATFORM="offscreen"
ai_token_widget\.venv\Scripts\python.exe -m unittest discover -s ai_token_widget\tests -t .

# phase-0 probe
python ai_token_widget\diagnose.py --json ai_token_widget\phase0_report.json
```

The widget hides to the tray; use the tray menu to quit. Launching it again
raises the existing window. Configuration lives in
`%APPDATA%\AITokenWidget\config.json`; use the gear button or tray →
`Settings…` for the common options, or edit the advanced fields while the
widget is stopped. The file stores:

```json
{
  "notifications_enabled": true,
  "notification_sound": false,
  "always_on_top": true,
  "opacity": 0.97,
  "collapsed": false,
  "low_quota_percent": 20,
  "muted_agents": [],
  "collapsed_groups": []
}
```

`low_quota_percent` is clamped to 1–50. `muted_agents` suppresses quota and
session-state alerts for those provider ids; adapter errors are always shown.
`collapsed_groups` records provider ids whose group is collapsed.
`notification_sound` is off by default and only applies while
`notifications_enabled` is true. `opacity` is clamped to 0.5–1.0;
`always_on_top` and `collapsed` control the window's stacking and compact start
state. The widget makes no network calls and does not use or store API keys.
Runtime errors are written to `%APPDATA%\AITokenWidget\widget.log` (rotated at
256 KB).

`--fixtures` on `diagnose.py` writes sanitized samples to `tests/fixtures/`.
Review them before committing; `phase0_report.json` is generated and git-ignored.

## Packaging and installer

Build from the repository root:

```powershell
# build-only dependency
ai_token_widget\.venv\Scripts\python.exe -m pip install -r ai_token_widget\requirements-build.txt

# run tests, build both executables, portable ZIP and (if available) installer
powershell -ExecutionPolicy Bypass -File ai_token_widget\packaging\build.ps1
```

`build.ps1` generates the icon/version resources from `__version__`, runs the
test suite, then produces:

- `ai_token_widget\dist\AITokenWidget\AITokenWidget.exe` — portable onedir app;
- `ai_token_widget\dist\AI-Token-Widget-<version>-win64-portable.zip` — portable
  archive;
- `ai_token_widget\dist\installer\AI-Token-Widget-<version>-setup.exe` — per-user
  installer, when Inno Setup 6 (`ISCC.exe`) is installed.

Useful switches: `-SkipTests`, `-SkipPortable`, `-SkipInstaller`.

The installer runs without administrator rights and installs under
`%LOCALAPPDATA%\Programs\AITokenWidget`. It can add an optional desktop shortcut
and an optional `Run`-key entry for starting with Windows (both unchecked by
default). Before replacing or removing files it asks a running widget to quit
cleanly, so an open tray instance does not leave the executable locked.
Uninstalling leaves `%APPDATA%\AITokenWidget` (configuration and log) in place.
The packaging build does not install or modify the Claude bridge: that remains a
separate opt-in action.

The packaged bridge is a console executable inside the app folder:

```powershell
$bridge = "$env:LOCALAPPDATA\Programs\AITokenWidget\AITokenWidgetBridge\AITokenWidgetBridge.exe"
& $bridge status
& $bridge install      # explicit opt-in; changes only statusLine
& $bridge uninstall    # restores the previous statusLine
```

If you installed to a custom directory, use that path instead. Re-run
`install` after moving the installation so the recorded command keeps pointing
at the bridge.

## Reliability and notifications

- The gear button or tray → `Settings…` opens a scrollable panel for
  notifications, the optional alert sound, the low-quota threshold (1–50%), the
  poll interval (2–60 s), per-provider alert mutes and window appearance
  (`Always on top`, `Start collapsed`, opacity and `Reset position`). Changes
  apply immediately and are saved to `config.json`.
- `Play a sound for new alerts` is off by default. When enabled, the Windows
  notification sound plays once per poll with at least one new alert; it is
  disabled while the main notifications switch is off.
- Tray → `Notification history…` lists up to 50 saved alerts, newest first,
  with a `Clear history` action. The history survives restarts and is stored in
  `%APPDATA%\AITokenWidget\notifications.json`.
- The panel also has `Open folder`, `Open log` and `Copy report`. The report is
  sanitized: provider counts, session states, timings, settings and adapter error
  labels, with no prompts, transcript text, session ids or project paths.
- The footer reports `updated Ns ago`, `refreshing…`, `refresh slow (Ns)` after
  15 seconds, `stale · last update …` when the snapshot is older than
  `max(30 s, 2 × poll + 5 s)`, or `refresh failed · last update …`. Slow and
  stale states are amber; errors are red.
- Opening the panel does not change the alert state until Save; raising or
  lowering the threshold re-seeds the tracker on the next snapshot so an existing
  condition is not re-announced.
- Per-provider mutes suppress quota and session-state alerts for Claude Code,
  Codex or OpenCode. Adapter errors are not muted because they indicate a broken
  data source rather than normal provider activity.
- The poll timer skips a tick while a refresh is in flight, and manual refresh
  requests are coalesced into one follow-up pass. Work always runs on a
  dedicated thread.
- A failed refresh does not clear the cards: the last snapshot stays visible
  and the footer shows `refresh: <ExceptionType>` plus its age.
- Quota alerts are aggregated per provider window, so several sessions sharing
  one account quota produce a single notification. The most constrained copy
  supplies the percentage.
- Alerts are edge-triggered. A quota that stays low, a session that stays
  rate-limited or a persistent adapter error notifies once; it notifies again
  only after recovering and crossing the condition again.
- Only the first three new alerts from one poll are shown as tray bubbles, to
  avoid a burst. The history still records every new alert from that poll.
- The tray menu has `Notifications` and `Notification sound` checkboxes; changing
  either persists the matching config field. The settings panel exposes the same
  switches alongside the threshold, poll interval and provider mutes.
- The single-instance guard is per-user and best-effort: if the local socket
  cannot be created, the widget still starts rather than hiding usage behind a
  broken lock.

## Grouping and filters

- Provider groups follow a fixed priority: Claude Code, Codex, OpenCode, then
  any unknown adapter alphabetically. Sessions keep the registry order inside
  each group (running, rate-limited, waiting, idle, error; newest first within a
  state).
- The group header shows session count, running count and flagged count. A
  flagged session is rate-limited/error, has a quota window at or below
  `low_quota_percent`, or has 10% or less context remaining.
- Collapsing a group writes its provider id to `collapsed_groups`; an empty
  filter result offers a `Clear filters` action.
- `All` shows every session, `Running` only sessions currently generating, and
  `Issues` only flagged sessions. Search is case-insensitive and requires every
  whitespace-separated term to match the project, model or agent label.
- Filters are intentionally not persisted: a restart always starts from `All`
  with an empty search, so a filtered view cannot hide sessions at startup.
  Collapse state, by contrast, is a layout preference and is persisted.

## Project organization and management load

- Sessions are grouped by normalized `cwd`. Sessions without a working directory
  are grouped by project name in an `unknown:<project>` bucket.
- The project section keeps the six projects with the highest total tokens.
  Ties fall back to latest activity and then folder name.
- Modified files are unioned across the project's sessions. A relative path is
  resolved against that session's `cwd`; a relative path without a known `cwd`
  is counted but not sized, so it cannot accidentally match a widget-relative
  file. A path is measured only once per project.
- Size is the file's current size on disk, not the cumulative number of bytes
  written during the session. A file that was deleted after the edit is counted
  as missing and contributes no bytes.
- The load score is a 0–1 composite: prompts 35%, context pressure 30%, API turns
  20% and model factor 15%. The prompt component is 65% frequency and 35% average
  prompt character count. Scores map to `LIGHT` (1–2), `MEDIUM` (3), `HEAVY` (4)
  and `VERY HEAVY` (5).
- Model classes are `reasoning`, `multimodal` and `general`. A nonzero reasoning
  token count wins over the model-id heuristic. The model factor is only a hint:
  it does not claim a model is more expensive or more capable.
- The index is intentionally relative to one local machine and recent activity.
  It is not a quota, billing or benchmark metric.

## Claude Code quota bridge (opt-in)

Claude Code does not write account rate limits to its transcripts. It does pass
them to a configured status-line command. `claude_statusline.py` captures that
payload and writes a small snapshot to
`%APPDATA%\AITokenWidget\claude_rate_limits.json`.

The commands below are the source-checkout form and require the virtual
environment. An installed build uses `AITokenWidgetBridge.exe` instead, as shown
in the packaging section above.

```powershell
# install (backs up only the previous statusLine value)
ai_token_widget\.venv\Scripts\python.exe -m ai_token_widget.claude_bridge install

# inspect what is configured and what was captured
ai_token_widget\.venv\Scripts\python.exe -m ai_token_widget.claude_bridge status

# undo: restores the previous statusLine or removes the field
ai_token_widget\.venv\Scripts\python.exe -m ai_token_widget.claude_bridge uninstall
```

- If a different `statusLine` is already configured, `install` refuses unless
  `--force` is passed; uninstall then restores the old value.
- The bridge command uses the current Python interpreter and this folder's
  `claude_statusline.py`; if you move the folder or delete the venv, reinstall.
- Snapshots older than 24 hours are ignored by the adapter.
- The bridge is intentionally tolerant of status-line schema changes: if it
  cannot find rate limits it leaves the previous snapshot in place and prints
  `Claude` rather than breaking the status line.

## Provider details

| Provider | Inventory | Token usage | Context window | Account quota | Modified files |
|---|---|---|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | exact per unique message (`message.usage`, deduped by message id) | estimated from model family | exact via opt-in status-line bridge | `Write` / `Edit` / `MultiEdit` / `NotebookEdit` tool inputs |
| Codex | `~/.codex/state_5.sqlite` `threads` | exact cumulative + per-turn; cached input is a subset of input | exact from rollout tail (model-specific, e.g. 475,000) | exact 5h/weekly; freshest account snapshot shared by all cards | `apply_patch` headers in the rollout tail; recent activity only |
| OpenCode | `~/.local/share/opencode/opencode.db` | exact `session_v2` totals + latest-message usage | exact from local models.dev catalog | unavailable locally | `edit` / `write` tool states in `session_message` |

### Claude Code

- Exact input, output and cache token counts are deduplicated by `message.id`
  and summed; the latest non-sidechain assistant message supplies current
  context usage. Synthetic messages are ignored.
- Transcripts are cached by `(mtime, size)`, so polling only re-parses changed
  sessions.
- Context windows are not in the logs: current Fable/Opus/Sonnet/Haiku 5.x
  families and Opus 4.6-4.8/Sonnet 4.6 are treated as 1M; other Claude models,
  including Haiku 4.5, as 200K. These are estimates and are labelled
  `Context (est.)`.
- Modified paths come from `Write`, `Edit`, `MultiEdit` and `NotebookEdit` tool
  inputs. Bash redirections or other shell writes are not inferred. Prompt count
  excludes tool-result records and sidechains; prompt amplitude is a character
  count only.

### Codex

- `state_5.sqlite` supplies inventory, model, cwd and cumulative tokens.
- The rollout tail supplies exact rate-limit windows, reset times and the
  context window. Expired windows roll over to 0% used.
- Codex input tokens already include cached input, so the card's `in` value
  does not add the cache a second time.
- Rate limits are account-wide. Every Codex card uses the freshest rollout
  snapshot with rate-limit windows rather than a per-session snapshot.
- Rollouts are read from the tail only and cached by `(mtime, size)`.
- Modified paths are best effort from `*** Add/Update/Delete File:` headers in
  `apply_patch` tool inputs inside that tail. Older edits outside the tail, and
  shell writes, may be missing. Prompt/API counts come from `response_item`
  messages and `token_usage_record` entries in the same tail.

### OpenCode

- `session_v2` (fallback: `session`) supplies inventory, cumulative tokens and
  cost; `session_message` supplies the latest per-message usage and whether the
  last turn is still streaming.
- The context window comes from the local `models-dev:catalog` row in `kv`.
  Only that row is read from `kv`; credential tables are never queried.
- The database is opened read-only and connections are closed after each poll.
- Prompt and assistant counts come from `session_message` rows; prompt amplitude
  uses the user row's `text` length. Modified paths come from completed `edit`
  and `write` tool items in `session_message`. OpenCode's `executed` flag is not
  reliable for completed tools, so `state.status` is authoritative. Shell
  writes are not inferred.

## Running state

Adapters decide whether a session is running from activity timestamps and turn
state (for example, an assistant message without `completed` in OpenCode). A
matching process only attaches its PID for display; process presence alone does
not promote an idle or waiting session to running.

Codex MSIX processes run from their install directory, so cwd matching often
fails. The registry then attaches an unmatched Codex process only to a session
that the adapter already considers running.

## Code layout

- `core/models.py`: `Session`, `Usage`, `Quota`, `QuotaWindow`, `Snapshot`.
- `core/agents.py`: canonical provider ids, labels and display order.
- `core/registry.py`: adapter fan-out, PID attachment, dedupe, ordering.
- `core/filters.py`: `All` / `Running` / `Issues` rules and search matching.
- `core/grouping.py`: provider grouping and per-group counts.
- `core/alerts.py`: edge-triggered quota/state/error notifications with
  per-provider mute filters.
- `core/notifications.py`: bounded persisted notification history and optional
  Windows alert sound.
- `core/config.py`: persisted window, notification, sound, mute and group-collapse
  settings.
- `core/logging_setup.py`: rotating log file and unhandled-exception hook.
- `core/diagnostics.py`: sanitized support report and refresh health summary.
- `core/model_limits.py`: Claude context-window estimates.
- `core/load.py`: model classification and the 1–5 management-load heuristic.
- `core/projects.py`: cwd grouping, unique modified-path sizing and project
  summaries.
- `sources/codex.py`: threads + rollout-tail quota/context, prompts and patch
  paths.
- `sources/claude_code.py`: transcript usage/context, prompts and write/edit
  paths + bridge quota.
- `sources/opencode.py`: SQLite sessions/messages, prompts and edit/write paths +
  models.dev context.
- `claude_statusline.py`: dependency-free status-line capture script.
- `claude_bridge.py`: opt-in install/uninstall/status CLI with field-level undo.
- `single_instance.py`: per-user local socket; second launch raises the window.
- `processes.py`: psutil scan; excludes the Claude desktop app and matches
  node-hosted agent packages by command line.
- `ui/refresh.py`: worker object that runs registry refreshes off the GUI thread.
- `ui/groups.py`: clickable, keyboard-accessible provider group headers.
- `ui/history.py`: notification history dialog with clear action.
- `ui/settings.py`: scrollable settings panel for notifications, sound,
  threshold, refresh interval, appearance, per-provider alert mutes and
  diagnostics shortcuts.
- `ui/projects.py`: project rows, modified-file totals and load badges.
- `ui/`: floating window, tray, filter bar, cards, context/quota bars.
- `packaging/`: PyInstaller specs and launchers, icon/version generation,
  `build.ps1`, and the Inno Setup installer script.
- `requirements-build.txt`: build-only dependencies (PyInstaller).

## Accuracy audit (2026-10-23)

The final audit compared adapter and card values with the real local stores:

- **Claude Code:** duplicate transcript records written for separate content
  blocks of the same API response were counted once by `message.id`. On this
  PC the cumulative session total dropped from 7.75M to 3.97M tokens, and the
  current context remained 164.8K.
- **Claude context:** the active `claude-haiku-5-5` model was incorrectly
  treated as 200K. Current 5.x families and the confirmed 1M legacy families
  are now 1M, so the card shows 164.8K / 1.0M instead of 164.8K / 200K.
- **Codex tokens:** `input_tokens` already contains
  `cached_input_tokens`; the card no longer adds the cache again. The audited
  session now shows `in 56.3M` rather than `in 112.2M`.
- **Codex quota:** cards now share the freshest account-wide rate-limit
  snapshot, avoiding different 5h/weekly values on sessions captured at
  different times.
- **Codex credits:** `has_credits=false` no longer renders as
  `Credits $0.00`; a rollout without usable windows shows quota unavailable.
- **OpenCode:** cumulative fields, latest-message context and catalog context
  limits matched the database and were left unchanged.

### v0.6.0 project/load audit

- **OpenCode modified files:** completed `edit`/`write` tools can still carry
  `executed=false`. Treating that flag as completion dropped every OpenCode file
  from the project view. The adapter now uses `state.status`; completed edits are
  counted, while running, pending and errored tools are skipped.
- **Path deduplication:** repeated writes to the same normalized path count once.
  Sizes are read with `os.stat`, so the project total is the current size of the
  touched files rather than the sum of every write payload.
- **Prompt amplitude:** the load index counts prompt characters but never stores
  prompt text. Frequency remains the larger prompt component (65%) so one huge
  paste does not dominate the index.
- **Real-data check:** after the OpenCode fix, the local project view reported
  modified files for the main OpenCode and Codex workspaces instead of showing
  zero edits.

## Known limitations

- OpenCode does not expose account quota locally; provider-specific quota (for
  example OpenRouter credits) is not implemented yet.
- Claude context windows are estimates, as described above. The estimate can
  still be wrong for a custom or future model id.
- Claude quota is unavailable until the opt-in bridge is installed.
- Codex quota is account-wide; the card shows the freshest snapshot with
  windows, which may be a few minutes behind the current time.
- Each adapter lists up to 12 sessions from the configured age window (24 hours
  by default, clamped to 1–168 hours).
- Claude transcripts are parsed in full when they change; this is cached and
  fine for normal session sizes.
- A worker read that hangs cannot be interrupted; the window stays responsive,
  but snapshots stop updating. The footer switches to `refresh slow` after 15
  seconds and then `stale`, and `Copy report` in Settings captures the timing and
  last successful snapshot.
- Notifications use tray bubbles, not the Windows notification center. The local
  history is capped at 50 entries and uses the Windows system notification sound;
  there is no custom sound picker or history export.
- Filters are session-only; there are no saved filter presets or provider-only
  filters. Collapse a provider group to hide it without filtering the data.
- Release binaries are unsigned, so Windows SmartScreen may warn on first launch.
  There is no auto-update mechanism; rebuild and reinstall to upgrade.
- The packaged GUI and bridge are x64 Windows builds. A 32-bit or ARM64 build
  would need a separate PyInstaller run.
- Project file totals only include tool-reported write/edit paths. Writes done
  through a shell command, a build step or an external editor are not counted.
- Codex modified paths are limited to the `1.5 MB` rollout tail. Edits from
  earlier in a long thread may be missing, so Codex project sizes are a
  recent-activity estimate.
- File size is the current size of each touched file, not the cumulative number
  of bytes written. A deleted file is counted as missing and contributes no
  bytes.
- Sessions without a `cwd` are grouped by project name; their relative modified
  paths are counted but cannot be sized safely.
- The project section shows the top six projects by token total. Projects below
  the cut are not shown in that section, though their session cards remain.
- The management-load index is a local heuristic based on recent activity. It is
  not a provider quota, billing estimate or benchmark, and prompt amplitude is a
  character count rather than a tokenizer result.

## Phase 0 findings (2026-10-22, this PC)

| Provider | Sessions | Token usage | Context window | Account quota |
|---|---|---|---|---|
| Claude Code | JSONL, 17 sessions | exact per message (`message.usage`) | not in logs | status-line bridge required |
| Codex | SQLite + JSONL, 70 threads | exact (`total_token_usage`) | **475,000** in logs | **exact** — 5h/weekly `used_percent` + reset |
| OpenCode | SQLite `session_v2` | exact aggregate columns | locally cached models.dev catalog | provider-dependent |

Notes that changed the plan:

1. **Codex needs no network calls for quota.** `event_msg/token_count` carries
   `rate_limits.primary/secondary` with `used_percent`, window length and
   `resets_at`; `state_5.sqlite` `threads` provides session inventory and
   `updated_at` for running detection.
2. **OpenCode uses SQLite** (`opencode.db`, `session_v2`), not JSON files. The
   `model` column is a JSON string such as
   `{"id":"...","providerID":"..."}` and must be parsed.
3. **Claude Code exposes usage but not quota.** Exact quota requires the
   status-line bridge that captures the status-line JSON.
4. **`claude.exe` is usually the Claude desktop app**, not Claude Code CLI.
   Process-name matching alone would produce false sessions; store activity is
   the source of truth.
5. Codex logs are long (35M+ tokens in one thread): quota must be read from the
   **tail**, never by parsing the whole file into memory.
