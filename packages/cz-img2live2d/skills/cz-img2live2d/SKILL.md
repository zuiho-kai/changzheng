---
name: cz-img2live2d
description: Use the Changzheng, PuppetLoom and Anime2.5DRig toolkit to turn character art into layered, rigged animated models through CLI operations, asset preparation, native editing, visual review and export.
---

# cz-img2live2d

You are the authoring agent. The package provides deterministic tools, native backends and evidence; use your own vision and available image tools to prepare artwork and judge the result.

## Begin

Run `cz-img2live2d doctor`. Explicitly configure missing engine roots using `configure`; pinned repositories and install commands are in the package README. Do not assume the parent Changzheng `.reference/` or credentials exist on another machine.

Create a separate project per character with `init --image <image> --project <new-dir>` or `init --psd <psd> --project <new-dir>`. An image-only project returns `needs_assets`: inspect the supplied art and prepare an aligned layered PSD using available decomposition/image editing tools. Preserve identity, canvas, pose and overlap. Check actual pixels and alpha after edits; prompt instructions are not proof of alignment or transparency. Attach with `assets --project <dir> --psd <file>`.

## Select and combine real capabilities

- Complete layered PSD: start with `build --backend puppetloom`. Its editing, revision, named actions and native output interfaces are available via `native`.
- Light PSD or missing eye/mouth variants: `build --backend anime25d`, then inspect `rig.json`, `layers.json` and actual preview. Its generic replacement artwork is marked `synthetic`; it is a starting point to review, not guaranteed character-specific art.
- Use `bridge --project <dir>` to transfer the Anime backend's original-canvas layers and supplements into a new PuppetLoom native project. It uses PuppetLoom's own supplement API for mouth variants. Transfer does not import foreign meshes or physics. Read accepted/rejected assets and final native checks.
- Existing aligned Changzheng assets: `assets --changzheng <dir>`, then `build --backend changzheng`. This preserves its MOC3 and frontend performance path. It is a named 1254-square character template, not a general image binding algorithm.

Keep builds separate and iterate on the same intended character. Do not substitute an unrelated reference image or silently alter the live avatar.

## Native authoring

Use `native --project <dir> -- describe` and `native -- capabilities`. Read the configured PuppetLoom root's `docs/AGENT_USAGE.md` for the needed operation only. Prefer its agent specification/plan/apply, author, calibrate, actions and history commands. Pass native arguments after `--`; the wrapper resolves the current backend directory.

Preserve native revision checks and asset acceptance. Do not directly rewrite `puppetloom.json` to bypass authoring. `awaiting-visual-review`, `needs-assets`, missing parts and disabled features retain their original meaning.

For Anime, get a native settings template from `review` or `window.cz.settings()` in the isolated preview, adjust its parameters/layer depth or order, and apply using `tune --settings <json>`. PSD fingerprint and layer IDs must match; use native value ranges. Re-review the new build.

## Review the actual result

In Changzheng, start `启动模拟器.ps1` and use only `simulator/workspace/` with localhost 17874. `review --project <dir> --backend <engine> --workspace simulator/workspace --audio <existing-clip>` stages a unique candidate and returns URL, screenshots, video and report. It does not replace the current simulator character. Outside Changzheng, provide an isolated served workspace and `--base-url`.

Open the neutral, speaking and stopped images and inspect the continuous recording at normal display scale. Look for identity/style changes, drifting eyes, face growth, gaps, clipped limbs, frozen mouth art and unnatural head/body motion. Use native high-resolution calibration sheets for specific shape issues: `review --backend puppetloom --native-sheet`.

Runtime parameter checks alone do not prove a visible blink or mouth change. A native project may disable mouth motion while its controller still accepts numeric mouth input. The recording is silent even when actual PCM drives the animation; do not claim audible speech quality, real microphone/camera acceptance or online TTS verification.

Return visual findings tied to the reviewed snapshot and revise the relevant native project or asset. Never convert `verify.valid` into visual acceptance. Preserve failed attempts and do not call an unreviewed model finished.

## Deliver

`export --project <dir> --backend <engine> --output <new-dir>` emits native model, sources and project record. Inspect all referenced files. PuppetLoom Cubism output additionally needs its native exporter configured and tested; Anime's PSD/browser rig is not a MOC3. Changzheng runtime JS is separate from the model and must accompany it to preserve the same performance.

Report what was actually built/rendered, remaining asset limitations and the usable artifact paths. Do not publish to the Changzheng `web/` directory or touch live port 17870 without a separate user publishing instruction.
