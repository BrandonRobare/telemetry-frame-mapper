# UX Audit — Telemetry Frame Mapper (frontend)

_Generated 2026-06-24 by a parallel run of 7 UX/design audit skills against the warm-light redesign (Tiers 1–3 + bulk editing). Read-only audit — no source was changed. Each lens invoked its skill directly (no rubric fallbacks)._

## Executive summary

The redesign is **genuinely strong and distinctive** — every lens independently rated the visual identity, motion, and domain materials well above typical internal-tool quality, and the AI-slop lens explicitly judged the glass + 2px-corner aesthetic as **earned identity, not slop**. The craft is real: the `StatusHud` telemetry strip, optimistic mutations with Undo toasts, teaching empty states, the tokenized warm palette, and the deliberate `--accent`/`--accent-strong` split all landed.

What holds it back is **two systemic, cross-cutting gaps**, each flagged by 4–6 of the 7 lenses:

1. **No visible keyboard focus anywhere** (`:focus-visible` absent app-wide; several `outline:none`). Highest-consensus, highest-impact finding.
2. **No responsive breakpoints** (0 `sm:`/`md:` across the codebase; Review grid hardcoded to 4 columns) + a cluster of **contrast failures** on `--text-faint` and `--accent`-as-text.

Fixing the P0 cluster below is mostly a handful of token/global-CSS edits that ripple everywhere.

## Per-lens scorecard

| Lens (skill) | Score / tally | Headline |
|---|---|---|
| design-critique | **Usability 7.5/10** | Strong IA + interactions; focus-state gap + fixed 4-col grid |
| accessibility-review | **14 WCAG AA failures** (~4 critical / 6 major / 4 minor) | Focus states, `--text-faint`, menu keyboarding, modal focus trap |
| design-system (design) | **Token adherence 7/10** | Excellent token design; ~61 hex literals duplicate token values |
| ux-copy | **7/10** | Terminology drift (Frames/Photos/Images); actionless errors |
| web-design-guidelines (Vercel) | **~28 violations** | Focus, aria-live toasts, forms autocomplete/focus, URL state |
| design-system (ECC) + slop | **Visual 7.8/10; "not slop"** | Identity is earned; a11y + responsive are the only real drags |
| ui-ux-pro-max (DB) | **Aligned by equivalence** | Style/type divergences are valid brand choices; gaps are structural (a11y/responsive) |

## Prioritized findings (deduped across lenses)

Severity reflects cross-lens consensus. "Flagged by" = how many of the 7 lenses raised it (confidence signal).

### P0 — Accessibility blockers (fix first)

**A1. No visible focus indicator, app-wide** · _flagged by 6/7_
`:focus-visible` exists nowhere in `frontend/src`; several controls set `outline:'none'` with no replacement ([ImportModal.tsx:225,255](frontend/src/features/import/ImportModal.tsx), [ReviewTab.tsx:152,188](frontend/src/features/review/ReviewTab.tsx), [Button.tsx:56](frontend/src/shared/components/Button.tsx), nav/Tools/StatsBar/BatchToolbar buttons). Keyboard users get no focus cue across the whole app. → Add a global `:focus-visible { outline: 2px solid var(--accent-strong); outline-offset: 2px }` in [index.css](frontend/src/index.css) and remove the `outline:'none'` overrides; give `Button` a `:focus-visible` ring. **One change fixes most of the cluster.**

**A2. `--text-faint #9A9078` fails text contrast** · _flagged by 5/7_
Computed **2.59–3.11:1** on the surfaces (below AA 4.5:1), yet used at 11px for meaningful labels in [StatusHud.tsx](frontend/src/shared/components/StatusHud.tsx) (STAGE/labels/session name), [ReviewTab.tsx](frontend/src/features/review/ReviewTab.tsx) batch-toolbar labels, and CornerTicks. → Darken to ≈`#7C725C` (~4.5:1 on `--surface`), or reserve `--text-faint` strictly for decorative text and use `--text-muted` for HUD readouts ([index.css:19](frontend/src/index.css)).

**A3. `--accent #B87C4C` as text / white-on-accent** · _flagged by 2/7 (a11y + DB)_
`--accent` as text is **3.09–3.43:1**; white on `--accent` is **3.43–3.49:1** — both fail AA. Matters because `--grad-splat` lightens toward `--accent` at the **top** of primary buttons ([Button.tsx:20](frontend/src/shared/components/Button.tsx)), so white button text can dip under 4.5:1 there. → Use `--accent-strong` for any accent-colored text; verify button text against the **lightest** gradient stop, not just `--accent-strong`.

**A4. Tools dropdown declares `role="menu"` but isn't keyboard-operable** · _flagged by 3/7_
No arrow-key/Home/End/Escape handling, no focus move into the menu on open, no return-focus on close; the outside-click closer is a bare `<div>` ([App.tsx:188-219](frontend/src/App.tsx)). 7 of 13 tabs live only here → keyboard users can't reach half the app. → Implement roving focus + Escape-to-close + focus management, or drop the menu ARIA for a plain disclosure of `<button>`s.

**A5. Modal has no focus trap; inputs lack autocomplete/error-focus** · _flagged by 2/7_
`role="dialog" aria-modal` but Tab can leave the dialog and focus isn't restored on close ([ImportModal.tsx:119](frontend/src/features/import/ImportModal.tsx)); inputs lack `name`/`autoComplete`/`spellCheck` and the first error isn't focused on submit. → Trap Tab within the dialog, restore focus to the trigger, add input attributes + focus-first-error.

**A6. Toasts not announced to screen readers** · _flagged by 2/7_
The toast container has no `aria-live`/`role="status"` ([ToastStack.tsx:14-15](frontend/src/shared/components/ToastStack.tsx)), so success/error/Undo are silent to SR. → Add `aria-live="polite"` (and `role="alert"` for errors).

### P1 — High-value usability / consistency

**B1. No responsive breakpoints; Review grid hardcoded to 4 columns** · _flagged by 3/7_
0 `sm:`/`md:` classes anywhere; `gridTemplateColumns: 'repeat(4, 1fr)'` ([ReviewTab.tsx](frontend/src/features/review/ReviewTab.tsx)) and fixed hero `height:250`/`maxWidth` won't reflow on narrow/split viewports. → Use `repeat(auto-fill, minmax(180px,1fr))` for the grid (matches the Overview stat grid) and add at least one mobile breakpoint for the hero/overview.

**B2. Hardcoded hex duplicating existing tokens** · _flagged by 3/7_
The exact token values are re-pasted as literals in three data-color sites: StatsBar array ([ReviewTab.tsx:121-125](frontend/src/features/review/ReviewTab.tsx)), `STAGE_COLORS` ([stages.ts:60-65](frontend/src/shared/pipeline/stages.ts)), and [LayerControls.tsx:6-9](frontend/src/features/map/LayerControls.tsx); plus raw `#FFFDF7` on-accent text in ~6 places. → One shared token-derived color map (resolve CSS vars once for Leaflet/canvas) + add an `--on-accent: #FFFDF7` token.

**B3. Terminology drift: Frames / Photos / Images** · _flagged by 2/7_
The same count is labeled three ways; [SessionSidebar.tsx:122-124](frontend/src/features/map/SessionSidebar.tsx) shows a "Frames" card (footprints) **and** a "Photos" card (`photo_count`) side-by-side, implying they differ. → Standardize on "Frames" everywhere; drop the redundant "Photos" card.

**B4. `splatBloom` animates `filter:blur` and ignores the in-app reduced-motion toggle** · _flagged by 2/7_
`filter` isn't compositor-friendly, and `MotionConfig reducedMotion="user"` only neutralizes transform/opacity for the **OS** query — it doesn't strip `filter` nor respond to the app's `data-reduced-motion` toggle ([motion/index.ts:21-25](frontend/src/shared/motion/index.ts), [App.tsx](frontend/src/App.tsx)). → Gate the variant on the `reducedMotion` setting; prefer transform/opacity.

**B5. Two parallel button systems + three badge implementations** · _flagged by 2/7_
A reusable `Button` exists but most screens re-roll inline buttons (divergent padding/borders/hover); badges have 3 looks (`Badge`, `STATUS_BADGE`, `FLAG_BADGE`). → Route actions through `Button`/`Badge`; this also makes the A1 focus fix land in one place.

**B6. Actionless errors + `alert()` inconsistency** · _flagged by 2/7_
"Could not load footprints — is the backend running?" (jargon, no action), "Failed to load storage info." (dead end), and raw `alert()` on delete failure ([StorageTab.tsx:39,139](frontend/src/features/storage/StorageTab.tsx)). → Add a recovery action/Retry; route errors through the toast system.

**B7. Status conveyed by color alone** · _flagged by 2/7_
Reprojection severity and StatsBar legend dots signal good/warn/bad by color only ([ReviewTab.tsx:339-351](frontend/src/features/review/ReviewTab.tsx)). → Add a non-color cue (icon/shape/text).

**B8. Primary nav/filter state isn't in the URL** · _flagged by 2/7_
`activeTab`, Review `activeFlag`/`sortBy`, Settings section are `useState`-only ([App.tsx](frontend/src/App.tsx)) — not linkable/bookmarkable/reload-safe. → Sync to query params (`?tab=review&flag=blurry`).

### P2 — Polish

- **Touch targets** — InfoHint "?" is 14×14 (min 24–44); small `✕ clear`/toolbar dot buttons too ([InfoHint.tsx:16](frontend/src/shared/components/InfoHint.tsx)). _(2/7)_
- **Missing loading states** — Overview stats and Reconstruct flash from empty→populated despite excellent loaders existing elsewhere. _(2/7)_
- **Type scale** — 122 magic `fontSize`/`fontWeight` literals (incl. `11.5`, `9`); no scale tokens. _(2/7)_
- **Disabled CTA copy** — "Reconstruction already in progress" is a sentence as a button label; point to the progress card instead. _(2/7)_
- **`Button` has no loading state** for long async actions (import/reconstruct/export) — the `.tg-indeterminate` keyframe could back a spinner. _(1/7)_
- **Capitalization** — Title Case headings/CTAs ("Start Reconstruction", "Quality Flags") vs. the app's sentence-case voice. _(1/7)_
- **Icon/glyph buttons** — `◈ ☀ ⊕ ✕ ▾` need `aria-label`/`aria-hidden` and `aria-pressed` on toggles. _(2/7)_
- **`index.html` title** is the placeholder `frontend`; no `<meta name="theme-color">`. _(1/7)_
- **Shadow tint untokenized** — `rgba(74,52,30,…)` embedded in `--shadow-1/2/3`; extract `--shadow-tint`. _(1/7)_
- **Badge universal sheen** — the radial-gradient gloss is applied to **every** badge ([Badge.tsx:28](frontend/src/shared/components/Badge.tsx)) — the one place a decorative effect is unconditional (mild slop-adjacent). _(2/7)_
- **Radius aliases** — `--edge`/`--radius-sm/md/lg` all = `var(--radius)` (2px); imply a scale that doesn't exist. _(2/7)_
- **Native `<select>` options / `window.confirm`** may render poorly on Windows dark mode; "Reset all settings" uses native confirm. _(1/7)_
- **Curly quotes** in body copy ("COLMAP's"); **Import CTA hint** `.mp4 · .srt · frames` mismatches the modal (JPEG folder only). _(1–2/7)_

## What's working (don't regress)

- **Visual identity is earned, not slop** (ECC slop lens): glass is *rationed* (refraction reserved for hero/map; `Panel` glass opt-in, refraction off by default; dense surfaces stay flat), the palette deliberately avoids purple-blue defaults, motion is domain-meaningful, and the `--grad-splat` gradient is a justified gaussian-splat metaphor.
- **IA**: pipeline spine + Tools dropdown is the right way to tame 13 tabs.
- **StatusHud** persistent telemetry, **optimistic mutations + Undo toasts**, **teaching empty states**, and **bespoke domain materials** (PointField, FrustumCard, HexPrismLogo3D color-tracking) are standout.
- **Token system** is well-designed; the `--accent`/`--accent-strong` split already pre-solves most contrast (verified `--accent-strong` 5.13–5.22:1).
- **Reduced motion** is unusually complete (OS query + in-app toggle + glass guards) — one gap: framer JS animations (B4).

## Coverage & method

All 7 lenses ran and are represented above; none was dropped. Each invoked its skill directly (design-critique, accessibility-review, design-system×2, ux-copy, web-design-guidelines [Vercel rules fetched live], ui-ux-pro-max [`search.py` run against its CSV DB]). Audit was static/code-based + computed contrast from `index.css` tokens; no source files were modified.

**Suggested fix order:** A1 (global focus) → A2/A3 (contrast tokens) → A6 (toast aria-live) → B1 (responsive/grid) → B2 (token color map + `--on-accent`) → B3 (terminology) → then P1/P2 as a polish pass.

---

## Fixes applied — 2026-06-24

Verified: production build passes · 48/48 tests · lint clean (1 pre-existing unrelated error in `HexPrismLogo3D.tsx`) · console clean · a11y snapshot + computed-style checks. (Browser screenshots were non-functional this session — verification was done via the accessibility tree and `getComputedStyle`.)

**Done (all P0 + most P1/P2):**
- **A1** Global `:focus-visible` ring in `index.css`; removed all 5 inline `outline:'none'` (ImportModal, ReviewTab ×2, SplatViewerTab).
- **A2** `--text-faint` darkened `#9A9078 → #756A52` (now ~4.7–5.2:1 on warm surfaces).
- **A3** Button gradient base → `accent-strong → accent-hover` (white text now 5.13:1+, was ~4.25:1); accent-as-text in GpsSync → `--success`.
- **A4** Tools dropdown keyboard support (Arrow/Home/End/Escape, focus into menu on open, return focus to trigger).
- **A5** ImportModal focus trap + restore-focus-on-close + `name`/`autoComplete`/`spellCheck` + recovery copy on errors.
- **A6** ToastStack `role="status" aria-live="polite"`.
- **B1** Review grid `repeat(4,1fr)` → `repeat(auto-fill, minmax(190px,1fr))`.
- **B2** Added `--on-accent` token (6 sites de-hardcoded); tokenized StatsBar dots, LayerControls, StorageTab `DIR_META`; documented `STAGE_COLORS` (must stay hex — feeds Three.js); dropped `#f85149` fallbacks.
- **B3** Terminology unified on "Frames" (ReviewTab "frames"; SessionSidebar `Mapped`/`Frames` instead of `Frames`/`Photos`).
- **B4** `splatBloom` gated on the in-app reduced-motion setting (+ softened blur).
- **B6** Error copy fixed (LeafletMap; StorageTab `alert()` → toast; ImportModal); RECON values mapped to friendly labels.
- **B7 (partial)** `aria-label`/`aria-pressed` on Review flag + usable toggles.
- Misc: `index.html` title + `theme-color`; import-CTA hint corrected (`.jpg frames in a folder`); "Run coverage analysis" sentence case.

**Deferred (rationale):**
- **B5** button/badge consolidation — large refactor; the focus-parity consequence is already solved globally by A1.
- **B8** URL/deep-link state — needs a router; feature-sized.
- Full responsive breakpoint sweep (hero/overview), type-scale tokens, touch-target enlargement, `--shadow-tint`, Badge sheen opt-in, remaining Title-Case labels, curly quotes, `window.confirm` → styled modal — polish/large; tracked here for a later pass.
- Pre-existing `react-hooks/refs` lint error in `HexPrismLogo3D.tsx` (untouched; fixing it re-times a ref the Three.js recolor effect depends on).

---

## Taste-skill pass + merge-readiness — 2026-06-28

Ran the Leonxlnx/taste-skill suite (`design-taste-frontend`) against the live UI to ready the redesign for a PR. This app is a multi-tab **product UI**, which is out of the skill's landing-page core scope, so its cross-cutting lenses were applied (AI-tells, contrast/a11y, color/shape/**theme** consistency locks, motion discipline, the Section 14 pre-flight); the `PipelineOverview` hero got the landing-page treatment.

**Context:** the branch was merged up onto current `origin/main` first. Upstream had since shipped a **dark theme** (`[data-theme="dark"]` token set in `index.css`, `theme`/`toggleTheme` in `mapStore`, a toggle in General settings), `lastActiveTab` persistence, and per-field settings validation. The merge unioned those with the redesign (glass system, tooltips, StatusHud, bulk-edit).

**Done:**
- **Dark mode completed.** Upstream's dark tokens didn't cover the redesign's additions, so the hero band and glass surfaces stayed light in dark mode (a Page-Theme-Lock violation). Added dark variants for `--glass-bg/border/spec`, `--shadow-1/2/3`, `--contour`, `--grid`, and tokenized the hero wash as `--topo-grad` (was hardcoded cream `#f2e7cb/#e4cfa4`). Verified both modes live; the toggle flips instantly with no reload.
- **Em-dash / en-dash sweep.** Replaced 20 visible-prose em-dashes (labels, errors, hints, options, toasts) with periods/colons/commas and 9 en-dashes in number ranges with hyphens. Kept the `—` empty-value placeholder in data tables (a standard data-UI convention; the skill scopes out data tables) and left non-visible code comments alone.
- **URL / deep-link state (audit B8).** New lightweight `shared/hooks/useUrlState.ts` (URLSearchParams + `history.replaceState`, no router). Wired `?tab=`, Review `?flag=`/`?sort=`, and Settings `?section=`. Bookmarkable + reload-safe; e.g. `?tab=review&flag=blurry`.
- **Badge sheen opt-in.** The universal radial gloss (flagged as mild slop, and too bright on dark badges) is now `sheen` opt-in, off by default.
- **InfoHint touch target.** Hit area enlarged to 24×24 while the visible "?" stays 14px.

**Verified green:** `npm run build` (tsc + vite), `npm run lint`, 73 frontend tests, 11 backend tests, console clean, both themes, deep-links, tablet width.

**Deferred (rationale):**
- **Button/badge full consolidation (B5)** — large cross-cutting refactor across 13 tabs; focus-parity is already solved globally by A1, so low risk/reward to rush. Badge sheen de-slop landed; full routing tracked for a focused follow-up.
- **Full mobile responsive** — the app degrades acceptably at tablet+ (max-width centering, auto-fit grids, scroll-on-overflow nav); a phone layout for a Leaflet-heavy desktop tool is low-value.
- **Polish** — `window.confirm` → styled modal (Settings reset), `--shadow-tint` extraction, type-scale tokens, `Button` loading state. Small, independent; tracked for a later polish pass.
