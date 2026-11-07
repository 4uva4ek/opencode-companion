# OpenCode Companion

Previously OpenCode Model Sync. Manage OpenCode models, agents, MCP servers, workspaces and settings in one desktop app. Existing configuration, language preferences and excluded workspaces are retained. The old `opencode-model-sync` command remains a compatibility alias.

[Русская версия](README.ru.md)

A small desktop app for Linux, macOS (Apple Silicon) and Windows. It asks your model servers which models they serve and adds them to the [opencode](https://opencode.ai) config. It requires OpenCode 2.x and works with the regular release: opencode picks up config changes on its own.

## Features

- Lists the providers in `~/.config/opencode/opencode.json` that have their own API address, and checks whether each server responds.
- Works with Ollama, LM Studio, vLLM, llama.cpp and any OpenAI-compatible server, local or on your network.
- For Ollama and LM Studio it reads the real context size and tool-calling support. Embedding models are skipped.
- **Sync** adds new models. **Remove from config** removes the models you select, for example ones that are gone from the server.
- Two independent buttons keep the same labels in both states. Highlighted means on; muted means off:
  - **Display** shows or hides the model in OpenCode's catalog through the config, preserving its settings.
  - **Tools** enables or disables tool-calling support.
- Only one Companion instance runs per user. Launching again brings the existing window forward, including from the tray. A crashed instance does not prevent the next launch.
- Finds local servers on their default ports that are not in the config yet and offers to add them.
- The config only changes when you press a button. A backup `opencode.json.bak-model-sync-*` is written next to it before the first change.
- Rename or remove a provider from its **⋯** menu. Renaming keeps its ID; removing also clears model selections that refer to it.
- The **Workspaces** tab lists the folders opencode works in and cleans up the rows that are stuck there.
- Lives in the tray. Light or dark theme follows the system. Russian and English interface.

Providers are read and written in the one map OpenCode 2.x reads: `providers`, spelled with `package`, `settings` and `capabilities`. The old `provider` map is neither read nor migrated: a file still holding it is the user's own to clean up, and the app leaves those keys on disk untouched while editing its own map. OpenCode 2.x ignores that map just as faithfully.

The **Settings** and **MCP** tabs can edit `.jsonc` while retaining comments and unchanged values. The existing provider sync and agent editing actions still refuse to rewrite files containing comments.

## Image input

The provider list shows **Images**, **No images**, or **Images ?** when capability information is unknown. Ollama's native `vision` capability, LM Studio's `vlm` type, and explicit input modalities/vision flags from compatible servers are recognized. Model names are not used to guess. Missing metadata (for example Strata's `iq3_s` listing) does not mean images are unsupported.

**Sync** now also fills missing image capabilities on existing models. Explicit input modality lists, including text-only lists, always win over server metadata. Other modalities, tool support, limits, names and overrides are retained. Use the **Images** switch on a configured model to enable or disable image input manually.

For a server without metadata, press **Test** beside the selected model. After confirmation, Companion sends up to two small randomized synthetic images to the OpenAI-compatible `/chat/completions` endpoint, outside the UI thread. This can load a model and incur generation costs; each request has a 60-second timeout. It sends no personal images and never runs generation during background discovery or Sync. HTTP 200 is insufficient: both responses must correctly identify the shapes, colors and positions. Errors, unsupported parameters and inconclusive answers leave support undetermined and the config unchanged. A successful test enables image input (and adds the model if it is new). Endpoint, model-ID and authentication overrides are respected; concurrent changes to the tested provider/model are detected before saving.

Image input is written in the words of the one map that is written:

- `providers` / `package` / `settings`: `models.<id>.capabilities.input = ["text", "image"]`, preserving the other capability fields.
- A provider that came from `provider` / `npm` / `options` arrives there through the same translation, so its `models.<id>.modalities` becomes `capabilities`.

Existing input/output modalities are preserved; disabling images removes only `image` from input. Saves use the normal backup and atomic write. As with other provider edits, commented JSONC is refused rather than rewritten; a visual test is not started when its result cannot safely be saved. These formats follow the [OpenCode 2.x provider config schema](https://github.com/anomalyco/opencode/blob/dev/packages/schema/src/config/provider.ts).

## Settings and MCP

Five independent tabs: Providers, Workspaces, Agents and teams, MCP, and Settings.

- Settings covers the `opencode.json` schema for OpenCode 2.1.4: 29 sections with nested fields, no superseded names. Categories and search include experimental settings such as `experimental.subagent_depth`.
- Finite choices use dropdowns; nested objects and ordered lists use forms. Arbitrary third-party SDK and plugin data uses JSON. Labels and hover descriptions support English and Russian.
- Not set leaves the field absent, preserving inheritance and OpenCode defaults. Project configuration and managed policies can override global values.
- MCP provides local and remote server creation, editing, removal and enable checkboxes backed by `disabled`. Server names stay constant; global timeouts expand separately.
- Save validates the schema, backs up the file, merges unrelated external edits and refuses conflicting changes. Drafts survive tab and language switches.
- Notices during editing and after saving explain when changes take effect. Server startup settings warn about a restart; integrations may need reconnection. OpenCode is never closed or restarted automatically.

## Agents and teams

The separate **Agents and teams** tab shows which model each opencode agent runs on and lets you change it. The model picker groups models by provider in collapsible sections.

- **Build a team**: a planner on a strong model plus several workers (coder, tester, reviewer, researcher or your own), each on its own model. The planner becomes a primary agent that may hand work only to its workers. With "only hands out work" checked, it cannot edit files or run commands. The workers become subagents, and each gets only the access its role needs: the tester cannot edit files, the reviewer and the researcher change nothing.
- **New agent** and **Edit**: name, description, kind (primary, subagent or both), model, instructions, temperature, access to file edits, commands and the web, and the subagents the agent may hand work to. The built-in agents `build`, `plan`, `general` and `explore` can be set up under their own names.
- Models are picked from the ones opencode has connected: the app asks opencode itself (`opencode models`), so the list holds your local models and free cloud models from opencode Zen and OpenRouter alike. The free, local and tool-calling labels and the context size come from the config and from the [models.dev](https://models.dev) catalog that opencode uses. The catalog is cached for a day. A model you switched off is left out of the list, which `opencode models` still reports. An agent whose model is not among the connected ones is flagged.

The app looks for the opencode command line on `PATH`, in the install script, npm and bun folders, and inside OpenCode Desktop on Windows, macOS and Linux. If it is somewhere else, set the `OPENCODE_CLI` environment variable to its path. If it cannot be found, the model list comes from the config.

New agents go to the `agent` section, whose format the opencode docs describe. An agent from the newer `agents` section is edited there, but its permission rules are kept as written. Settings the app does not manage, such as `color` or `steps`, are kept.

## MCP catalog

Open **MCP → Add from catalog**. Sources:

- **Starter collection** — offline recipes for Context7, Sentry and Grep from the [OpenCode examples](https://opencode.ai/docs/mcp-servers/#examples), plus Playwright and GitHub from their publishers' instructions.
- **Official MCP Registry** — live latest-version search and cursor pagination through the public [registry API](https://registry.modelcontextprotocol.io/).
- **Glama** — source repositories and remote connectors. The [Glama directory API](https://glama.ai/mcp/reference) requires a key: enter it in the catalog window or set `GLAMA_API_KEY` before launching. An entered key is kept only for that window, is not written to OpenCode's configuration, and is never sent to another catalog. Listings link back to Glama and advertising is labeled.

Choose a server and connection option, then **Configure and add…**. Review the URL or exact command, choose a unique name, add HTTP headers or environment variables, and optionally leave the server disabled. Values may reference OpenCode's environment with `{env:NAME}`. Local recipes require Node.js (`npx`), uv (`uvx`) or Docker; Companion does not install those runtimes. Browsing never executes a package.

When a source has no usable connection metadata, open its publisher instructions and enter a URL or command manually. Unsupported package arguments also require manual setup. Package commands are never guessed from repository names. Existing names cannot be overwritten.

Adding creates a draft on the MCP page. Press **Save** to write it to `mcp.servers`, the OpenCode 2.1.4 format used by the settings editor. Comments in JSONC and unrelated settings are preserved, with a backup before replacement. Saving an enabled server allows OpenCode to connect or run its command. OAuth servers need a subsequent sign-in in OpenCode or `opencode mcp auth NAME`. Inspect connection status with `opencode mcp list`.

## Workspaces

Database reading supports the OpenCode 2.x schema (`session_v2`, `worktree`); on an older database the page stays readable and simply shows no sessions. Missing activity timestamps fall back to project timestamps. Removal/archive controls are disabled when the database does not support them; **Exclude** remains available without changing OpenCode.

The **Workspaces** tab lists the folders opencode works in and the git worktrees made from them, the same list opencode shows in its sidebar. Rows for folders that are no longer on the disk stay there for good, and opencode has no screen to clean them up.

- **Exclude** hides a workspace in this app only. opencode is not touched and the folder stays where it is. "Show excluded" brings the hidden rows back; **Bring back** returns one of them.
- **Remove** asks opencode itself. A worktree goes away through `DELETE /api/worktree`, removed the way opencode created it; when it holds changes that are not committed, the app asks a second time before dropping those. A project folder is archived in opencode's database, which is how opencode takes it off its own list — the folder and its sessions stay, and opening the folder in opencode shows it again.
- What opencode has archived is off this page, exactly as it is off opencode's own list. "Show archived" brings those rows into view, and **Back from the archive** clears the mark so the workspace is on the list of opencode again.
- **Add folder** hands a folder to the running opencode, the same way opening a folder there registers it.
- A row says whether its folder is still on the disk, whether it is a git worktree, how many sessions opencode has saved for it, and when it was last used. The **⋯** menu opens the folder.

While opencode runs, the list comes from it through `opencode api`; otherwise the same rows are read from `~/.local/share/opencode/opencode.db`. opencode's database is copied to `opencode.db.bak-model-sync-*` before anything is written to it. Which workspaces are excluded is this app's own file, `~/.config/opencode/model-sync-workspaces.json`.

## Updates

Click the **version number beside the language switch → Check for updates**. Companion checks the latest stable GitHub release for this OS and architecture. Choose **Download update**, then **Install and restart**. Downloads are verified against SHA-256 checksums; the app closes before its installation directory is replaced. The previous version is retained at the backup path shown in the dialog, and a failed directory replacement restores it. OpenCode configuration is outside the installation and is preserved.

Automatic installation requires a packaged app in a writable location. On macOS, move the app to a writable Applications folder before updating. Windows replaces the entire application folder after exit; Linux updates the existing installation folder. Unsupported architectures, missing release assets, verification failures and network errors are reported without replacing the app. Source checkouts are updated through Git. Checking and installing are user-initiated; there are no silent background installations.

## Download

Builds for every platform are attached to the [latest release](../../releases/latest). The builds are not signed:

- **macOS:** unzip, then right-click the app and choose **Open** the first time.
- **Windows:** extract into a new empty folder and run `OpenCode Companion.exe`. Do not unpack over an older build: obsolete DLLs may prevent startup. SmartScreen may ask you to confirm.
- **Linux:** unpack the archive and run `opencode-companion/OpenCode Companion`.

## Run from source

You need [uv](https://docs.astral.sh/uv/).

```bash
uv run opencode-companion
```

## Build

Each platform builds its own app:

```bash
uv run python scripts/build.py
```

The result is in `dist/`: an `.app` on macOS, a folder with an `.exe` on Windows, a folder with an executable on Linux, plus an archive. To add it to the Linux application menu:

```bash
sh scripts/install-linux.sh
```

GitHub Actions builds all three platforms. Pushing a `v*` tag runs the `build` workflow and attaches the builds to a release.

## Tests

```bash
uv run pytest
```
