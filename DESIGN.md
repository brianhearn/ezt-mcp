---
version: 0.1.0
date: 2026-05-06
status: draft-scaffold
source_product: EZT Designer V2
owner: EasyTerritory
intended_consumers:
  - AI coding agents
  - EZT MCP Map Component
  - future EasyTerritory web UI components
tokens:
  colors:
    # TODO: Benton/his agent should extract these from EZT Designer V2.
    # Use semantic names first; raw hex values second.
    brand_primary: TBD
    brand_secondary: TBD
    surface: TBD
    surface_muted: TBD
    text_primary: TBD
    text_secondary: TBD
    border: TBD
    success: TBD
    warning: TBD
    danger: TBD
    map_territory_palette: []
  typography:
    font_family_sans: TBD
    font_family_mono: TBD
    base_size: TBD
    scale: {}
  spacing:
    unit: TBD
    scale: {}
  radii:
    sm: TBD
    md: TBD
    lg: TBD
  shadows: {}
  components: {}
---

# DESIGN.md — EasyTerritory Product Design System

This file captures the visual design language of **EZT Designer V2** in a format AI coding agents can read and apply consistently. It combines machine-readable design tokens in YAML frontmatter with human-readable rationale, constraints, and component guidance in Markdown.

The first concrete consumer is the **EZT MCP Map Component**. The broader goal is consistency across the EasyTerritory product stack.

## Source of Truth

The design source is Benton's EZT Designer V2 UI. This scaffold intentionally does not invent final colors, typography, spacing, or component values. Benton's agent should extract them from the real application and screenshots, then update this file.

## Design Principles

- **Professional geospatial SaaS.** The interface should feel credible for enterprise sales, operations, and territory-planning users.
- **Map-first clarity.** UI chrome supports the map; it should not compete with territory geometry, labels, or analysis overlays.
- **Dense but readable.** Territory planning is information-rich. Prefer compact controls, clear hierarchy, and legible labels over oversized consumer-app spacing.
- **Calm decision support.** Use color intentionally for territory distinction, warnings, exceptions, and metric variance. Avoid visual noise.
- **Consistent with Designer V2.** The Map Component should feel like it belongs to the same product family, even when embedded in an agent host.

## Required Token Categories

Benton's agent should populate at least:

1. **Color tokens**
   - brand colors
   - surface/background colors
   - text colors
   - border/divider colors
   - semantic status colors
   - territory palette colors
   - metric variance palettes

2. **Typography tokens**
   - font families
   - base font size
   - heading/body/caption scale
   - label and map-callout typography

3. **Spacing and layout tokens**
   - base spacing unit
   - panel padding
   - toolbar/control spacing
   - legend density

4. **Component tokens and patterns**
   - buttons
   - inputs/selects
   - tabs
   - cards/panels
   - dialogs/popovers
   - legends
   - map callouts
   - layer toggles
   - metric badges

5. **Map-specific styling**
   - territory fill/stroke defaults
   - selected part highlight
   - hover state
   - inactive/disabled territory state
   - point symbol defaults
   - label defaults
   - basemap preference

## Agent Instructions

When generating EasyTerritory UI:

- Read this file before creating or modifying UI.
- Prefer semantic tokens over hardcoded values.
- If a needed token is missing, choose the closest existing semantic token and leave a TODO rather than inventing a new visual language.
- Keep the Map Component visually consistent with EZT Designer V2 while respecting host constraints such as OpenClaw Canvas or Microsoft Teams.
- Do not clone Designer wholesale. Reuse the design language; keep the Map Component lightweight and focused.

## Map Component Guidance

The EZT MCP Map Component should use this design system for:

- toolbar and mode controls
- legend styling
- layer visibility controls
- territory labels
- selected/hovered part styling
- metric badges and variance indicators
- read-only sharing chrome
- empty/loading/error states

The map itself may use TS presentation metadata for data-driven symbology. This DESIGN.md controls the product chrome and default visual language; TS presentation metadata controls solution-specific styling.

## Extraction Process

Recommended process for Benton's agent:

1. Inspect EZT Designer V2 screens and source styles.
2. Extract raw CSS/design values.
3. Convert raw values to semantic tokens.
4. Capture recurring component patterns with screenshots or references.
5. Populate this file.
6. Generate a small visual audit page showing tokens/components.
7. Have Benton review and approve.

## Open Questions

- Which exact Designer V2 screens are canonical for extraction?
- Are there dark-mode requirements?
- Which territory color palette is preferred for high-cardinality territory maps?
- Should Map Component controls match Designer V2 exactly or use a lighter embedded variant?

