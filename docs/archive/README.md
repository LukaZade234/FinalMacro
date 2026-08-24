# Archived docs

Kept so nothing is lost. Do not treat these as current product docs.

| File | Why it is here | When to open it |
|------|----------------|-----------------|
| [`mudae-tools-dev-guide.md`](mudae-tools-dev-guide.md) | Claude rebuild spec for [colblitz.com/mudae](https://colblitz.com/mudae/) solvers + calculators. | Porting `$oh`/`$oc`/`$oq`/`$ot` logic, perk 9 / `$bw` math, or any **Colblitz tools** item in [`TODO.md`](../TODO.md). Start with the section you need (§2–§9); do not paste the whole file into an LLM. |
| [`finalmacro-gallery-v3.html`](finalmacro-gallery-v3.html) | Static Run-page gallery (four layouts × palettes). | New shell, Run redesign, or palette/layout exploration. Open in a browser; implement in `gui/shells/` + `palettes.js` / `skins.js`. |
| `mudaebot-project-index.md` | Map of the previous CustomTkinter MudaeBot. | Historical only — use [`ARCHITECTURE.md`](../ARCHITECTURE.md). |
| `MULTI_ACCOUNT.md` | Original Phase D write-up. | Historical only — folded into [`ARCHITECTURE.md`](../ARCHITECTURE.md). |
| `MUDAE_SETTINGS_COMMANDS.md` | Verbatim live `$settings` capture (gitignored). | Parser audit; summarized in [`MUDAE_LOGIC.md`](../MUDAE_LOGIC.md). |

**Current docs:** [`MUDAE_LOGIC.md`](../MUDAE_LOGIC.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`TODO.md`](../TODO.md)

### Quick paths

- **Colblitz / minigame solver work** → [`TODO.md` § Colblitz tools](../TODO.md) + [`mudae-tools-dev-guide.md`](mudae-tools-dev-guide.md)
- **New UI layout or theme** → [`ARCHITECTURE.md` § Appearance](../ARCHITECTURE.md) + [`finalmacro-gallery-v3.html`](finalmacro-gallery-v3.html) + `scripts/ui_preview.py`
