# Discovery UI-First Report

Date: 2026-03-23

## Purpose

This report captures the first practical decision for TomeHub Discovery:

- build `Discovery` as a separate page first
- make it the default landing surface
- validate the interaction model in frontend before locking backend contracts

This is the correct order for this feature because Discovery is not a normal CRUD screen. It is a composition surface. The real question is not only "which data do we have?" but also "which kinds of cards feel meaningful together?"

## Why UI First Makes Sense

Discovery mixes multiple content classes:

- internal library items
- internal notes and highlights
- unfinished research paths
- external cultural and academic signals
- synthetic LLM guidance cards

If backend work starts too early, the team risks hardening the wrong payload shape.

The better sequence is:

1. define the visible sections and interaction patterns
2. see which cards feel redundant, weak, or missing
3. infer the feed contract from the UI
4. then implement backend aggregation and ranking around that contract

This reduces wasted backend work and makes personalization rules easier to reason about.

## Implemented V0 Frontend Direction

The current prototype introduces a dedicated `Discovery` surface with these UI blocks:

- hero discovery card
- world feed cards
- archive-led theme suggestions
- continue / reopen cards
- unexpected connection cards
- one-click research actions

The page is intentionally interactive even before backend integration:

- users can switch lenses such as `ALL`, `WORLD`, `LIBRARY`, `REOPEN`
- internal cards can open real TomeHub items
- action cards can jump into existing product surfaces like `LogosChat`, `Flux`, notes, and books

## Product Boundary

Discovery should not simply duplicate Dashboard.

Recommended distinction:

- `Dashboard` = counts, structure, system state
- `Discovery` = motion, curiosity, re-entry, prompts

This means Discovery should prefer:

- theme cards
- continuation cards
- suggestion cards
- synthesis cards
- external-world prompts

And avoid turning into:

- count tiles
- distribution grids
- admin summary panels

## Planned Feed Inputs

### Internal inputs

- books
- articles
- personal notes
- highlights
- favorites
- currently reading items
- dormant items
- tags / themes
- later: memory profile, Explorer sessions, unfinished paths

### External inputs

- PoetryDB
- Gutendex
- Google Books / Open Library
- OpenAlex / Crossref / Semantic Scholar / arXiv
- Europeana / Internet Archive / Art Institute of Chicago
- TMDB for media extensions

## Recommended Backend Follow-Up

After the UI stabilizes, backend should expose a single normalized feed contract, for example:

- `card_type`
- `origin` (`internal`, `external`, `synthetic`)
- `title`
- `summary`
- `reason`
- `theme`
- `source`
- `image_url`
- `target_type`
- `target_id`
- `cta_label`
- `priority`

Frontend should render from that unified contract instead of calling many providers directly.

## Immediate Next Step

Use the new page for product review first:

- which sections feel strong
- which cards feel unnecessary
- whether Discovery should lean more editorial or more utilitarian
- whether Explorer / LogosChat / Flux handoff is clear enough

Only after that should the backend feed and scheduler be finalized.
