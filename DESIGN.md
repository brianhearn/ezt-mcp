---
version: 0.2.0
date: 2026-05-08
status: draft-extracted
source_product: EZT Designer V2
source_product_surfaces:
 - https://app-ezt-staging.azurewebsites.net (Next.js portal — Dashboard, Maps, Roster, Business Data, Users, API Keys)
 - easyterritory-portal/ (shared component source for the portal and the PBI visual)
 - easyterritory-visual/ (Power BI custom visual V2 composition root and Azure Maps overrides)
 - easyterritory-landing.html (brand / marketing surface)
owner: EasyTerritory
intended_consumers:
 - AI coding agents
 - EZT MCP Map Component
 - future EasyTerritory web UI components
tokens:
 colors:
  brand_primary: '#00d4aa' # teal — CTAs, active state, focus glow, "live" indicators
  brand_secondary: '#00b894' # teal-dim — pressed / secondary brand fill
  brand_hover: '#00e6b8' # solid teal CTA :hover
  brand_glow: 'rgba(0, 212, 170, 0.15)' # halo behind hero badges, focused-input ring tint
  surface:
   dark:
    primary: '#0a1628' # app / map background
    secondary: '#111d33' # sidebar, header strips
    tertiary: '#1a2940' # hovered surface
    elevated: '#2a3a52' # raised cards
    input: '#1e293b' # form fields
    panel: '#0f1d32' # docked panels
    overlay_95: 'rgba(10, 22, 40, 0.95)'
    overlay_85: 'rgba(10, 22, 40, 0.85)'
    overlay_60: 'rgba(10, 22, 40, 0.60)'
   light:
    primary: '#f8fafc'
    secondary: '#f1f5f9'
    tertiary: '#e2e8f0'
    elevated: '#cbd5e1'
    input: '#ffffff'
    panel: '#f0f4f8'
    overlay_95: 'rgba(248, 250, 252, 0.95)'
    overlay_85: 'rgba(248, 250, 252, 0.85)'
    overlay_60: 'rgba(248, 250, 252, 0.60)'
  surface_muted:
   dark: 'var(--hover-overlay-subtle)' # rgba(255,255,255,0.06)
   light: 'var(--hover-overlay-subtle)' # rgba(0,0,0,0.03)
  text_primary:
   dark: '#f0f4f8'
   light: '#0f172a'
  text_secondary:
   dark: '#94a3b8'
   light: '#475569'
  text_muted:
   dark: '#64748b'
   light: '#94a3b8'
  border:
   dark:
    muted: 'rgba(255, 255, 255, 0.04)'
    subtle: 'rgba(255, 255, 255, 0.06)'
    default: 'rgba(255, 255, 255, 0.10)'
    strong: 'rgba(255, 255, 255, 0.20)'
   light:
    muted: 'rgba(0, 0, 0, 0.05)'
    subtle: 'rgba(0, 0, 0, 0.08)'
    default: 'rgba(0, 0, 0, 0.12)'
    strong: 'rgba(0, 0, 0, 0.18)'
  success: '#22c55e' # success toasts, "Geocoded" chip, completed cycles
  warning: '#f59e0b' # in-product warning (clock/icon glyphs, alert banners, intent="warning" toasts)
  warning_pill: '#fde047' # trial/billing-attention pill (yellow Fluent Badge on navy ink). Distinct from `warning`.
  danger: '#ef4444' # error toasts, destructive confirmations
  scenario: '#a855f7' # scenarios panel, working-copy banner, "Account-based" map-type pill (paired with #c084fc text)
  info_chip: '#64748b' # mono codes, count meta
  map_territory_palette:
  - '#00d4aa'
  - '#6366f1'
  - '#f59e0b'
  - '#ec4899'
  - '#06b6d4'
  - '#8b5cf6'
  - '#10b981'
  - '#f97316'
  - '#3b82f6'
  - '#ef4444'
  - '#14b8a6'
  - '#a855f7'
  - '#84cc16'
  - '#e879f9'
  - '#22d3ee'
  - '#facc15'
  - '#fb923c'
  - '#34d399'
  - '#818cf8'
  - '#f87171'
  metric_variance:
   up: '#22c55e' # ▲ positive delta
   down: '#ef4444' # ▼ negative delta
   flag: '#f59e0b' # ◆ needs review
 typography:
  font_family_sans: 'DM Sans, system-ui, -apple-system, sans-serif'
  font_family_mono: 'JetBrains Mono, monospace'
  base_size: '14px'
  line_height_body: 1.6
  line_height_marketing: 1.7
  scale:
   xxs: '10px' # uppercase section labels (panel headers)
   xs: '11px' # counts, codes, micro-meta, mono IDs
   sm: '12px' # floating-panel titles, dense body
   base: '14px' # default UI body, nav, list rows
   md: '16px' # panel / dialog titles
   lg: '20px' # section H3
   xl: 'clamp(28px, 4vw, 44px)' # marketing section titles
   hero: 'clamp(40px, 6vw, 72px)' # marketing hero h1
  label: 'DM Sans 10px semibold uppercase tracking-wide'
  map_callout_label: 'DM Sans 12px semibold opacity 0.85'
  code_chip: 'JetBrains Mono 11px'
 spacing:
  unit: '4px' # Tailwind default 4px scale
  scale:
   sidebar_row: '10px 12px' # sidebar nav item padding
   top_bar: '16px 32px' # app top bar padding
   map_header: '0 12px (h-10)'
   panel_header_row: '0 12px 8px 12px'
   panel_body: '0 16px 12px 16px'
   dialog_field_gap: '16px (space-y-4)'
   search_dropdown_row: '10px 12px'
 radii:
  sm: '4px' # chips, color swatches
  md: '6px' # buttons, inputs, search field
  lg: '8px' # nav links, status pills, search dropdowns
  xl: '12px' # floating panels, docked panel cards, map mockup
  xxl: '16px' # marketing / pricing cards
  pill: '9999px' # hero badges, "Most Popular" pill
 shadows:
  panel: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' # shadow-2xl on floating panels (frost + this)
  popup: '0 3.2px 7.2px rgba(0,0,0,.132), 0 0.6px 1.8px rgba(0,0,0,.108)' # Azure Maps popup override
  tile_hover: '0 12px 40px rgba(0,0,0,0.3)' # marketing feature card hover
  marketing_glow: '0 0 0 1px rgba(0,212,170,0.05), 0 25px 80px rgba(0,0,0,0.5), 0 0 120px rgba(0,212,170,0.05)'
 motion:
  theme_transition: '0.2s ease (background-color, color)'
  hover_transition: '0.15s (transition-colors)'
  sidebar_collapse: '0.2s ease (width)'
  panel_slide: '0.3s ease-in-out (right)'
  nav_progress: '2s cubic-bezier(0.4, 0, 0.2, 1) keyframe `nav-progress` (asymptotic to 93%)'
  brand_pulse: '2s ease-in-out infinite (opacity 1→0.3) — restricted to one element per surface'
  reduce_motion: 'all decorative animations honor prefers-reduced-motion: reduce'
 components:
  button_primary:
   bg: brand_primary
   hover_bg: brand_hover
   text: 'surface.dark.primary (navy ink on teal)'
   radius: lg
   padding: '10px 22px'
   hover_lift: 'translateY(-1px) + shadow 0 8px 30px rgba(0,212,170,0.3)'
  button_outline:
   bg: transparent
   border: border.default
   text: text_primary
   hover_border: brand_primary
   hover_text: brand_primary
  button_subtle: 'Fluent <Button appearance="subtle"> — top bar, icon buttons in app shell'
  button_transparent: 'Fluent <Button appearance="transparent"> — row actions in lists'
  accent_pill:
   bg: 'rgba(0, 212, 170, 0.10)'
   border: 'rgba(0, 212, 170, 0.30)'
   text: brand_primary
   size: xs
   weight: medium
   radius: md
  danger_button:
   text: '#f87171'
   hover_bg: 'rgba(239, 68, 68, 0.10)'
  input:
   bg: surface.input
   border: border.default
   focus_border: 'rgba(0, 212, 170, 0.50)'
   radius: lg
   padding: '8px 10px'
   mono_variant: 'bg surface_muted + font-mono for codes/IDs'
  card:
   bg: surface.secondary
   border: border.subtle
   radius: xl
   padding: '20px'
  floating_panel:
   bg: 'surface.overlay_95 + backdrop-filter: blur(4px)'
   border: border.default
   radius: xl
   shadow: shadows.panel
   drag_strip: 'dedicated row, w-8 h-1 rounded-full bg-gray-500/50 grip'
   title_row: 'text-xs font-semibold sentence-case (NOT 10px uppercase muted)'
   dismiss: '20×20 Dismiss icon, p-1 rounded-md, gray-400 → text_primary on hover'
   shells:
    FILL: 'h-full min-h-0 — resizable Rnd panels (Realign, Stats, Scenarios)'
    FIT: 'auto height — compact toolbars (Lasso, Click-Edit, State assign)'
    DIALOG: 'auto height with max-h-[90vh] — Travel Ring, Distance dialogs'
  dialog:
   provider: 'Fluent UI v9 Dialog'
   mount: '.ezt-dialog-mount portal node inside scaled FluentProvider subtree (PBI visual requirement)'
   footer: 'Cancel (subtle, left of primary) + Save / primary (teal, right)'
  toast:
   provider: 'Fluent Toaster (single ToastProvider) at position=top'
   timeouts: { error: 6000, default: 4000 }
   forbidden: 'window.alert / window.confirm / window.prompt are banned (rule: easyterritory-no-alert)'
  role_badge:
   icon: 'ShieldKeyhole24 (Filled when active row, Regular otherwise)'
   sizing: 'text-[11px] font-semibold rounded-md px-2 py-0.5; bg = color @ 15% alpha; ink = color full'
   owner: '#f59e0b' # amber
   admin: '#a855f7' # purple
   editor: '#00d4aa' # teal
   viewer: '#64748b' # slate
  status_pill:
   neutral_count: 'rounded-full border border-default px-3 py-1 text-[11px] text-text_secondary (e.g. "0 keys", "1/3 users")'
   map_type: 'rounded-md bg-[scenario]/15 text-[#c084fc] text-[11px] font-medium px-2 py-0.5 (e.g. "Account-based")'
   dataset_ready: 'rounded-md bg-brand_primary/15 text-brand_primary text-[11px] font-medium px-2 py-0.5 (e.g. "Ready", "Geocoded ✓")'
   dataset_failed: 'rounded-md bg-[danger]/15 text-[#f87171] text-[11px] font-medium px-2 py-0.5'
   trial_top_bar: 'Fluent Badge appearance="filled" color="warning" — yellow #fde047 bg, navy ink — links to /billing'
   "you": 'rounded bg-hover-overlay text-text_muted text-[10px] px-1.5 py-0.5'
  legend_swatch:
   size: '12px × 12px'
   radius: sm
   ring: 'ring-1 ring-white/10 (panel) or ring-white/20 (dialogs)'
  wizard_step_indicator:
   active: 'circle 32×32 bg-brand_primary text-navy scale-110'
   complete: 'circle 32×32 bg-brand_primary/20 text-brand_primary, checkmark inside'
   pending: 'circle 32×32 bg-input text-text_secondary'
   connector: '1px line, bg-brand_primary/40 if past step else bg-slate/50'
   file: 'easyterritory-portal/src/components/shared/WizardStepIndicator.tsx'
 map:
  engine: 'Azure Maps Web SDK (atlas)'
  sdk_load: 'AzureMapsContext (portal) / CDN powerbi.easyterritory.com (visual). Never call loadAzureMapsSDK() directly.'
  basemap:
   dark: 'Night (re-bind on theme toggle)'
   light: 'Road (re-bind on theme toggle)'
   attribution: 'Azure Maps default — never hide or recolor'
  control_bar:
   placement: 'top-center inside map canvas, z-[50]'
   size: '32×32 buttons, rounded-md, shadow'
   dark: 'bg surface.secondary text text_primary hover surface.tertiary'
   light: 'bg white text #333 hover bg gray-100'
   active: 'bg brand_primary text navy'
   order: 'zoom-in (+), zoom-out (−), basemap dropdown (Night/Road), address search, lasso, eraser/clear callouts'
  territory:
   fill_opacity_dark: 0.55
   fill_opacity_light: 0.35
   stroke_width: 1.5
   stroke_width_hover: 2
   stroke_width_selected: 2.5
   hover_fill_opacity_boost: 0.15
   selected_halo: 'white #ffffff @ 0.5 opacity, 4px outer stroke beneath colored stroke'
   edit_target_dash: 'stroke-dasharray 4 3, rotating 8s'
   dissolved_seams: 'never render duplicate internal seams between same-territory parts'
   label_placement: 'pole-of-inaccessibility (NOT centroid) so labels stay inside dissolved shapes'
   label_text: 'DM Sans 12px / 600 / opacity 0.85, color = territory color, 1px halo in surface.primary on low-contrast basemaps'
  drawing:
   stroke: 'brand_primary 2px solid'
   fill: 'rgba(0, 212, 170, 0.15)'
   vertex_handle: '6px white circle with 2px teal stroke'
   snap_indicator: '1px teal dashed crosshair under cursor'
  travel_ring:
   fill_opacity: 0.18
   stroke_opacity: 0.9
   stroke_dash: '6 4'
  distance_line:
   color: brand_primary
   width: 2
   label: 'mono distance value (mi/km)'
  zoom_pill:
   placement: 'bottom-left of map, z-[15]'
   bg: surface.overlay_95
   border: border.default
   radius: pill
   padding: '4px 12px'
   text: 'JetBrains Mono 11px brand_primary'
   theme_behavior: 'stays dark on both themes (sits over map, not over chrome)'
  edit_cta:
   placement: 'bottom-right of map, spans right-dock width minus 16px gutter'
   idle_label: 'Edit territories'
   idle_style: 'bg surface_muted, border brand_primary @ 30%, text brand_primary, pencil icon'
   active_label: 'Exit edit mode'
   active_style: 'bg brand_primary, text navy, font-semibold'
  popup:
   chrome: 'override Azure Maps default — display: block; box-shadow: none; + shadows.popup; border-radius 0'
   pinned_callout: 'use floating_panel chrome (radius xl, frost, shadow.panel)'
  legend:
   floating: 'bottom-4 left-4, w-64 max-h-[50vh], floating_panel chrome with bg-navy-mid/95 backdrop-blur-md'
   embedded: 'no border/background, fills the docked column'
   header: 'text-[10px] font-semibold uppercase tracking-wide text-text_muted'
   count: 'text-[11px] font-mono text-text_muted'
  z_index:
   map_header: 10
   map_control_bar: 50
   edit_overlays: 55
   rnd_panels: 56
   side_panel_handle: 15
   search_dropdown: 90
   fluent_dialog_mount: 999999 # escapes nested transform stacking contexts in PBI visual
---

# DESIGN.md — EasyTerritory Product Design System

This file captures the visual design language of EZT Designer V2 in a
format AI coding agents can read and apply consistently. It combines
machine-readable design tokens in YAML frontmatter with human-readable
rationale, constraints, and component guidance in Markdown.

The first concrete consumer is the **EZT MCP Map Component**. The broader
goal is consistency across the EasyTerritory product stack.

## Source of Truth

The design source is **Benton's EZT Designer V2 UI**. As of `version 0.2.0`,
"Designer V2" is interpreted as the union of:

- The signed-in Next.js portal at
 [`https://app-ezt-staging.azurewebsites.net`](https://app-ezt-staging.azurewebsites.net)
 (Dashboard, Territory Maps, `/maps/[id]`, Roster, Business Data, Users,
 API Keys). Crawled live on 2026-05-08 to extract chrome, tokens, and
 component patterns.
- The Power BI custom visual V2 (`easyterritory-visual/`), which already
 shares the portal's Fluent brand variants, CSS variables, and
 `FloatingPanelChrome` primitives 1:1 via webpack aliases.
- The brand / marketing surface (`easyterritory-landing.html`) for hero
 treatments, marketing buttons, and the brand mark.

The marketing domain `easyterritory.ai` is currently a "Launching Soon"
placeholder and is **not** a source of truth.

If "EZT Designer V2" is meant to refer to a separate surface (e.g. a
Figma library or a different build), this section needs to be
re-pointed and the tokens re-extracted — see Open Questions §1.

## Design Principles

1. **Professional geospatial SaaS.** The interface should feel credible
 for enterprise sales, operations, and territory-planning users.
2. **Map-first clarity.** UI chrome supports the map; it must not
 compete with territory geometry, labels, or analysis overlays.
 Panels, toolbars, and stats are overlays *around* the map, never the
 primary canvas.
3. **Dense but readable.** Territory planning is information-rich.
 Prefer compact controls (`text-xs`, 32×32 icon buttons,
 `rounded-md`), clear hierarchy, and legible labels over oversized
 consumer-app spacing.
4. **Calm decision support.** Use color intentionally for territory
 distinction (the 20-color categorical palette), warnings,
 exceptions, and metric variance. Avoid visual noise — the brand
 pulse is reserved for one element per surface.
5. **Consistent with Designer V2.** The Map Component should feel like
 it belongs to the same product family even when embedded in an
 agent host (OpenClaw Canvas, Microsoft Teams, MCP-rendered HTML).
6. **Dark by default.** The brand identity (navy + teal + neon-on-dark
 map) is primary. Light theme must work, but defaults bias dark.
7. **Restraint over decoration.** No emoji in product chrome. No
 gradients on body copy. No illustrations outside the marketing
 surface. Marketing exclamation marks belong on the marketing
 surface, not in the product.

## Required Token Categories

All concrete values live in the YAML frontmatter at the top of this
file. The categories below summarize what's populated and what
deliberately remains TBD.

### Color tokens — populated

- Brand: `brand_primary`, `brand_secondary`, `brand_hover`, `brand_glow`.
- Surface (dark + light): `primary`, `secondary`, `tertiary`,
 `elevated`, `input`, `panel`, `overlay_{95,85,60}`.
- Text (dark + light): `text_primary`, `text_secondary`, `text_muted`.
- Border (dark + light): `muted`, `subtle`, `default`, `strong`.
- Semantic: `success`, `warning`, `warning_pill` (yellow trial pill —
 intentionally split from `warning` amber), `danger`, `scenario`,
 `info_chip`.
- **Territory palette**: `map_territory_palette` — fixed 20-color array
 in fixed order. Index modulo 20 when there are more territories.
 Persist the assigned color on the territory record; never re-derive
 on render.
- Metric variance: `up` (green ▲), `down` (red ▼), `flag` (amber ◆).

### Typography tokens — populated

- `font_family_sans`: DM Sans (Google Fonts, weights 300/400/500/600/700,
 optical-size axis 9..40).
- `font_family_mono`: JetBrains Mono (weights 400/500). Used for
 territory codes, ZIP/FIPS IDs, percentages, the zoom pill, faux-terminal
 marketing chrome.
- `base_size`: 14px. Body line-height 1.6 (1.7 marketing).
- Scale: `xxs (10) / xs (11) / sm (12) / base (14) / md (16) / lg (20) /
 xl (clamp 28→44) / hero (clamp 40→72)`.
- Font smoothing: `-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale`
 globally, to keep rendering identical at every PBI viewport scale.

### Spacing tokens — populated

- `unit: 4px` (Tailwind default).
- Canonical paddings observed in chrome are listed in YAML
 (`tokens.spacing.scale`).

### Radii tokens — populated

- `sm 4 / md 6 / lg 8 / xl 12 / xxl 16 / pill 9999`.

### Shadows / elevation — populated

- `shadows.panel` (frost + shadow-2xl combo for floating panels over the
 map).
- `shadows.popup` (Azure Maps popup override).
- `shadows.tile_hover` (marketing feature-card hover).
- `shadows.marketing_glow` (multi-layer teal glow on hero map mockup).

### Motion tokens — populated

- Theme / hover / sidebar collapse / panel slide / nav progress / brand
 pulse durations + easings, plus the `prefers-reduced-motion`
 contract.

### Component tokens — populated

- `button_primary`, `button_outline`, `button_subtle`,
 `button_transparent`, `accent_pill`, `danger_button`.
- `input` (with mono variant).
- `card`, `floating_panel` (with the three shells: FILL / FIT / DIALOG),
 `dialog`, `toast`.
- `role_badge` (Owner / Admin / Editor / Viewer with shield icon and
 color).
- `status_pill` (`neutral_count`, `map_type`, `dataset_ready`,
 `dataset_failed`, `trial_top_bar`, `"you"`).
- `legend_swatch`.
- `wizard_step_indicator` (filed at `WizardStepIndicator.tsx`).

### Map-specific styling — populated

- `tokens.map.basemap` (Night dark / Road light, swap on theme toggle).
- Territory fill / stroke / hover / selected / edit-target / dissolved
 / label-placement specs.
- `drawing` (lasso / draw stroke + fill + vertex handle + snap
 indicator).
- `travel_ring`, `distance_line`.
- `zoom_pill` (bottom-left of map, mono, dark on both themes).
- `edit_cta` (bottom-right of map; idle teal-outline →
 active teal-fill).
- `popup` (Azure Maps default override + pinned-callout uses
 floating_panel chrome).
- `legend` (floating + embedded variants).
- `z_index` ladder for in-map layers.

### Tokens still TBD

- **Exact Azure Maps `style` parameter strings.** The dropdown labels
 are `Night` / `Road`; the underlying `atlas.Map({ style: ... })`
 literal needs to be confirmed (likely `night` and `road`, but may
 be `grayscale_dark` depending on the SDK version).
- **Logo lockup variants** (monochrome on light, monochrome on dark,
 favicon set, on-photo). Today the red polygon glyph is used on both
 themes — pending Benton's confirmation that this is final and not
 placeholder.
- **Print / export typography defaults.** Confirm whether territory
 codes in PDF/PNG exports use JetBrains Mono (we ship it) or a
 document-friendly substitute.

## Agent Instructions

When generating EasyTerritory UI, an agent MUST:

1. **Read this file before creating or modifying UI.** Tokens, chrome
 patterns, and map conventions live here.
2. **Prefer semantic tokens over hardcoded values.** Reference
 `tokens.colors.brand_primary` rather than `#00d4aa` in code, and
 use the CSS variables (`var(--bg-primary)`, `var(--text-primary)`,
 etc.) in the portal/visual codebase.
3. **If a needed token is missing, choose the closest existing
 semantic token and leave a `TODO: tokens.xxx`** rather than
 inventing a new visual language.
4. **Compose chrome from the prescribed primitives** — `PortalShell`
 for the app shell, `MapLayoutHeader` for the map header,
 `FloatingPanelChrome` (FILL / FIT / DIALOG shells +
 `FloatingPanelDragStrip` + `FloatingPanelHeaderRow`) for any
 draggable panel over the map. Don't re-invent the shells.
5. **Keep the Map Component visually consistent with EZT Designer V2
 while respecting host constraints** such as OpenClaw Canvas or
 Microsoft Teams. The MCP variants in §"Map Component Guidance"
 below are the sanctioned reductions.
6. **Do NOT clone Designer wholesale.** Reuse the design language;
 keep the Map Component lightweight and focused on map + minimal
 chrome.

### Hard rules (non-negotiable)

1. **No new colors** outside `tokens.colors.*` and
 `tokens.colors.map_territory_palette`.
2. **No new fonts** — DM Sans + JetBrains Mono only.
3. **No `alert` / `confirm` / `prompt`.** Use the Fluent `Dialog` or
 the `ToastProvider` (workspace rule `easyterritory-no-alert`).
4. **No logo above the map.** The logo lives in the app-shell sidebar.
 The map header is hamburger + address search only (or the PBI
 visual top strip in PBI builds).
5. **No uppercase `text-[10px]` muted labels on draggable panel
 headers.** Floating-panel titles are `text-xs font-semibold
 text-[var(--text-primary)]` sentence case.
6. **No bypassing `useEtApi()`** for data fetching in shared
 components (workspace rule `shared-components`).
7. **No direct `loadAzureMapsSDK()` calls.** Use `AzureMapsContext`.
8. **No stripped focus rings.** `:focus-visible` MUST render the teal
 2px outline (`outline: 2px solid var(--teal); outline-offset: -2px`).
9. **No animated text or backgrounds at >0.3 opacity changes** in
 product chrome. The brand language is restrained. Decorative
 pulses are reserved for the marketing surface and a single "live"
 indicator per surface.

## Map Component Guidance

The EZT MCP Map Component should use this design system for:

- toolbar and mode controls
- legend styling
- layer visibility controls
- territory labels
- selected / hovered part styling
- metric badges and variance indicators
- read-only sharing chrome
- empty / loading / error states

The map itself may use **TS presentation metadata** for data-driven
symbology. This `DESIGN.md` controls the **product chrome and default
visual language**; TS presentation metadata controls
**solution-specific** styling (per-territory overrides, customer-defined
metric ramps, etc.).

### Chrome layout (default — full)

When the MCP renders a map for an agent or downstream consumer, it
defaults to a layout indistinguishable from the portal's `/maps/[id]`
page (so any output an agent composes feels like it was built inside
EasyTerritory):

```
┌─────────────────────────────────────────────────────────────────────┐
│ Map header (h-10): hamburger + address search │
├──────────────────────────┬──────────────────────────────────────────┤
│ LAYERS (left dock, │ ┌─────── In-map control ────┐
│ collapsible) │ │ + − [Night▼] ⌕ ⊙ ⌫ │
│ - REFERENCE LAYERS │ └────────────────────────────┘
│ - DATA LAYER NAME + │ │
│ │ MAP CANVAS │
│ │ │
│ │ │
│ │ TERRITORIES │
│ │ (right dock, │
│ │ collapsible) │
│ │ │
│ ‹ collapse handle │ [Zoom: 4.0] [✎ Edit territories ›] │
└──────────────────────────┴──────────────────────────────────────────┘
```

### Chrome variants (sanctioned reductions)

- **Headless map.** Map canvas only — no header, no docks, no
 control bar. The MCP must still publish the CSS variable set from
 `tokens.colors.*` on `:root` and apply the `dark` (or `light`)
 class so any portaled tooltips / popups inherit the theme.
- **Embedded card.** Map inside a `rounded-xl` frame with
 `shadows.panel` and the floating-panel frost overlay — used in
 agent-generated reports.
- **Read-only print / export.** Strip the in-map control bar and the
 Edit CTA, keep the legend, render territory codes in mono. The
 zoom pill is omitted (scale bar takes its place if needed).
- **Host-constrained (OpenClaw Canvas / Teams).** Default to the
 PBI visual top strip (28–32px tall) instead of the full app
 sidebar. The 4-icon top bar (settings / export / save-copy /
 fullscreen) is optional — drop any icons the host doesn't need.

### Floating panels — must reuse the primitives

Reuse the chrome primitives from
`easyterritory-portal/src/components/maps/FloatingPanelChrome.tsx`:

- Wrap with `react-rnd`, `dragHandleClassName` matching the
 `<FloatingPanelDragStrip dragHandleClassName="..." />`.
- Use one of `FLOATING_PANEL_SHELL_FILL` (resizable bound),
 `FLOATING_PANEL_SHELL_FIT` (auto-height, compact toolbars), or
 `FLOATING_PANEL_SHELL_DIALOG` (auto-height with `max-h-[90vh]`).
- Title row via `<FloatingPanelHeaderRow title={…} headerActions={…}
 onClose={…} />`. Title is **`text-xs font-semibold sentence-case`**.
- Header actions are **accent pill** buttons, never raw text links.

### Empty / loading / error states

- **Empty:** centered, faint outline icon (Fluent regular variant of the
 section's icon, ~32×32, `var(--text-muted)`) + primary line in
 `text-sm text-[var(--text-secondary)]` + optional helper line in
 `text-xs text-[var(--text-muted)]` + optional accent-pill CTA.
- **Loading:** in-place spinner — `w-3 h-3 rounded-full border-2
 border-[var(--text-muted)] border-t-[var(--teal)] animate-spin`.
 Page-level loading uses the 3px teal `nav-progress` bar described in
 `tokens.motion.nav_progress`.
- **Error:** Fluent `MessageBar intent="error"` inline (matches
 `TerritoryDetailsPanel` pattern). For destructive actions, prefer a
 Fluent `Dialog` confirmation.

## Extraction Process

Recommended → **Performed** on 2026-05-08:

1. ✅ Inspected EZT Designer V2 surfaces (live staging crawl with the
 browser MCP — `/login`, `/signup`, `/dashboard`, `/maps`,
 `/maps/[id]`, `/roster`, `/business-data`, `/users`, `/settings`
 in both dark and light themes; Map Settings dialog opened; Edit
 mode toggled).
2. ✅ Extracted raw CSS / design values from
 `easyterritory-portal/src/app/globals.css`,
 `easyterritory-visual/style/visual.less`,
 both `tailwind.config.*`, `FluentProvider.tsx` (brand variants),
 and `easyterritory-landing.html` (marketing tokens).
3. ✅ Converted raw values to semantic tokens (this file's YAML
 frontmatter).
4. ✅ Captured recurring component patterns and noted the canonical
 files in §References below.
5. ✅ Populated this file (`version 0.2.0`).
6. ⏳ **TODO:** Generate a small visual audit page showing the
 tokens/components in situ (token swatches + component gallery).
 Recommended location: `ezt-mcp/audit/` as a static HTML page so
 any agent / reviewer can open it without a build step.
7. ⏳ **TODO:** Have Benton review and approve.

## Open Questions

(The first four questions are inherited from `version 0.1.0`; the
remainder were added during the 2026-05-08 extraction pass.)

1. **Which exact Designer V2 screens are canonical for extraction?**
 `version 0.2.0` treats the staging portal's Dashboard, `/maps`,
 `/maps/[id]`, Roster, Business Data, Users, and API Keys as
 canonical. Confirm — and add any screens that are intentionally
 excluded (e.g. SuperAdmin, Tenants).
2. **Are there dark-mode requirements?** Both themes are populated.
 `dark` is the documented default. Confirm whether the MCP must
 ship light support or may dark-only initially.
3. **Which territory color palette is preferred for high-cardinality
 territory maps?** `tokens.colors.map_territory_palette` is the
 current 20-color sequence (sourced from
 `easyterritory-portal/src/types/territory.ts`). Confirm whether to
 wrap modulo 20 for >20 territories, or define a secondary palette.
4. **Should Map Component controls match Designer V2 exactly or use a
 lighter embedded variant?** §"Map Component Guidance" sanctions
 four variants (full / headless / embedded card / print). Confirm
 the default for MCP-hosted output.
5. **Azure Maps `style` parameter exact strings.** Dropdown labels
 are `Night` (dark) / `Road` (light). What literal does the portal
 pass to `atlas.Map({ style: ... })`?
6. **Trial yellow vs in-product warning amber.** `tokens.colors`
 currently splits these (`warning_pill: '#fde047'` for the trial
 badge, `warning: '#f59e0b'` for in-product alerts). Confirm the
 split is intentional and not a drift to fix.
7. **Is the red polygon glyph the final logo on light backgrounds?**
 It's currently used on both themes — confirm or supply a
 monochrome / inverted variant.
8. **Realign / Stats / Scenarios panel parity.** The staging tenant
 has 0 territories, so these panels could not be exercised live in
 the 2026-05-08 crawl. Tokens were extracted from the source files
 (`RealignPanel.tsx`, `TerritoryStatsPanel.tsx`, `ScenariosPanel.tsx`).
 Confirm against a populated tenant or send screenshots.
9. **Staging gaps that the MCP should not inherit:**
 - `/billing` returns the default Next.js 404, but it's linked from
 the sidebar and the Trial banner CTA.
 - `/terms` and `/privacy` 404, linked from the auth-card footer.
 - The 404 page itself is unstyled (default Next). Should be
 replaced with a branded surface using the auth-shell chrome.
10. **Agent-rendered HTML embedding.** Should MCP-generated reports
 embed a static screenshot of the map or a live MCP Map Component
 iframe? This determines whether the "embedded card" or "print"
 variant from §"Map Component Guidance" is the report default.

## References (canonical files)

| Concern | File |
|---------|------|
| Tailwind tokens (portal) | `easyterritory-portal/tailwind.config.ts` |
| Tailwind tokens (visual) | `easyterritory-visual/tailwind.config.cjs` |
| CSS variables (portal) | `easyterritory-portal/src/app/globals.css` |
| CSS variables + map overrides (visual) | `easyterritory-visual/style/visual.less` |
| Fluent brand variants & theme | `easyterritory-portal/src/components/layout/FluentProvider.tsx` |
| App shell (sidebar + top bar) | `easyterritory-portal/src/components/layout/PortalShell.tsx` |
| Map header | `easyterritory-portal/src/components/maps/MapLayoutHeader.tsx` |
| Floating-panel chrome primitives | `easyterritory-portal/src/components/maps/FloatingPanelChrome.tsx` |
| Legend pattern | `easyterritory-portal/src/components/maps/TerritoryLegend.tsx` |
| Right-dock pattern | `easyterritory-portal/src/components/maps/TerritoryDetailsPanel.tsx`, `TerritoryStatsPanel.tsx` |
| Wizard step indicator | `easyterritory-portal/src/components/shared/WizardStepIndicator.tsx` |
| Toast pattern | `easyterritory-portal/src/components/shared/ToastProvider.tsx` |
| Territory categorical palette | `easyterritory-portal/src/types/territory.ts` (`TERRITORY_COLORS`) |
| PBI visual composition root (top strip, dialog mount, scale handling) | `easyterritory-visual/src/MapShell.tsx`, `easyterritory-visual/src/visual.ts` |
| Brand surface (hero, marketing CSS, animations) | `easyterritory-landing.html` |
| Floating-panel rule (workspace) | `.cursor/rules/easyterritory-floating-panels.mdc` |
| Shared-components rule (no Next imports, `useEtApi`) | `.cursor/rules/shared-components.mdc` |
| No-alert rule (workspace) | `.cursor/rules/easyterritory-no-alert.mdc` |
| Live signed-in surface | https://app-ezt-staging.azurewebsites.net |
