# Emoji marks

`starwish.png` (⭐), `locked.png` (🔐), `owned.png` (✅) and
`server_disabled.png` (🚫) are the marks Mudae prints on list rows, drawn by
**Advisor › Lists** (`gui/views/MudaeListsView.qml`, the `Mark` component).

They are shipped as images rather than drawn from a font because a system
emoji font cannot be relied on: one machine had Twemoji installed and drew
them, another had none and showed empty boxes.

Rendered at 64×64 from **Twemoji** by Twitter, Inc. and other contributors,
licensed under **CC-BY 4.0** (https://creativecommons.org/licenses/by/4.0/).
Source: https://github.com/twitter/twemoji (graphics; no changes beyond
rasterising).
