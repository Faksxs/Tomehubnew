# TomeHub Discovery / Mainboard Architecture Plan

Date: 2026-03-22

## Purpose

This report captures the agreed product and architecture direction for a new `Discover / Mainboard` page in TomeHub.

The goal is to create a dynamic, living entry surface that is separate from the existing `Dashboard`.

Core rule:

- `Dashboard` remains the metrics and state surface
- `Discover / Mainboard` becomes the motion, curiosity, and next-action surface

This avoids duplicating counts and summary widgets across two places.

## Product Positioning

The new page should answer:

- What can I explore today?
- What meaningful external content is relevant now?
- What should I continue, reopen, or investigate deeper in Explorer?

It should not answer:

- How many books do I have?
- How many notes do I have?
- What are my aggregate dashboard totals?

Those stay in `Dashboard`.

## High-Level UX Structure

Recommended page structure:

1. `Hero Discovery`
   - one strong editorial card
   - example: artwork, poem, paper, open-access book, historical object
   - primary CTA: `Open in Explorer`

2. `Today From the World` (Modern API Selection)
   - **Art:** Rijksmuseum, The Met, Art Institute of Chicago.
   - **History:** Wikimedia "On This Day" (Historical events, births, deaths).
   - **Science:** NASA APOD (Astronomy Picture of the Day).
   - **Philosophy/Wisdom:** ZenQuotes, Stoic Quotes API.

3. `For Your Themes`
   - cards linked to user interest profile, memory profile, or library themes

4. `Continue / Reopen`
   - dormant paths, unfinished threads, previously touched themes.

5. `Unexpected Connection` (The Synchronicity Engine)
   - serendipity cards connecting internal and external knowledge via LLM.
   - example: Connecting a historical event from today to a book in user's library.

6. `Brain Explorations` (Different Mindset Alternatives)
   - **Micro-Exhibition:** 3 related artworks from different museums on a single AI-curated theme.
   - **Forgotten Gems:** A note/article from user's library related to current monthly themes.
   - **LLM Synthetic Wisdom:** AI-generated "Thought Experiment" or "Thesis of the Day" specifically for the user.

     - connect this poem to my notes

## Design Principles

- editorial, not admin-panel
- card-based, not metric-grid
- strong hero area
- visible source labels
- short context, clear CTA
- mobile-friendly rails or stacked cards
- no repeated dashboard counters

Conceptual distinction:

- `Dashboard = State`
- `Discover = Motion`
- `Explorer = Depth`
- `Flow = Drift`

## Data Sources

Discover should be hybrid, not external-only.

### 1. Fully Dynamic (Live APIs)
- **Visuals:** NASA APOD, Rijksmuseum, The Met, Artic.
- **Academic:** OpenAlex, arXiv, Semantic Scholar, Crossref.
- **Inspiration:** ZenQuotes, StoicAPI, Wikimedia OnThisDay.

### 2. Semi-Dynamic (LLM Synthesis & Alternatives)
- **Synchronicity Engine:** LLM-driven pairing of external daily facts with internal library items.
- **RSS Feeds:** Parsing philosophy/science journals (e.g. Aeon) and summarizing via LLM.
- **Local Discovery:** Random "Forgotten Note" injection based on theme similarity.

### 3. Static/Curated (Database)
- **Library Items:** notes, highlights, articles, cinema records.
- **Curated Classics:** A rotating set of high-quality "evergreen" content from the local DB.


## Architectural Direction

Frontend should not call multiple external APIs directly.

Recommended backend pattern:

- new aggregator endpoint such as `/api/discover/feed`
- backend normalizes cards into a common schema
- frontend renders one feed contract

Suggested normalized card shape:

- `card_type`
- `domain`
- `title`
- `subtitle`
- `snippet`
- `provider`
- `source_url`
- `image_url`
- `cta`
- `reason`
- `generation_mode`

## Feed Generation Strategy

The preferred v1 model is precomputed feed generation, not live fan-out on each page load.

Recommended flow:

1. scheduled job runs daily
2. curated candidates are fetched from selected external providers
3. items are normalized and lightly ranked
4. results are saved to Oracle-backed discover feed storage
5. frontend reads from cached backend output

Benefits:

- faster page load
- better API quota control
- safer failure handling
- stable curation quality
- "today's discovery" feeling

## Scheduler Recommendation

Initial recommendation:

- backend service + cron-based daily job

Possible schedule:

- every day around `03:00`

Example daily collection mix:

- 1 poem
- 1 artwork
- 1 book
- 2-3 academic items
- optional 1 archive/history object

Airflow should remain a later-stage option when orchestration becomes more complex.

Use Airflow later if needed for:

- retries and backfills
- multi-step pipelines
- dependency visibility
- richer observability

## Personalization Strategy

Personalization should be planned now but introduced in phases.

### Phase 1

- curated global or lightly personalized feed
- minimal user-specific weighting
- low operational risk

### Phase 2

- use `memory_profile`
- theme-aware selection
- examples:
  - physics-focused users see more `arXiv/OpenAlex physics`
  - history-focused users see more `Europeana/Internet Archive`
  - literature-focused users see more `Gutendex/PoetryDB/Google Books`

### Phase 3

- adaptive per-user ranking
- combines:
  - memory profile
  - library content
  - Explorer history
  - dormant paths
  - recent activity

Important decision:

- personalization should be architecturally supported from day one
- but full personalization should not block v1

## What Discover Should Not Duplicate

Do not repeat the following from `Dashboard`:

- total books count
- total notes count
- total films count
- summary metric tiles
- category distribution boxes
- aggregate progress counters

If any dashboard component is later moved, that should be a deliberate follow-up decision, not part of initial Discover scope.

## Recommended V1 Sections

The strongest v1 is:

- `Hero Discovery`
- `Today From the World`
- `Continue / Reopen`
- `Unexpected Connection`
- `Open in Explorer`

`For Your Themes` can be shallow in v1 and deeper in v2.

## Risks

Main risks:

- external API rate limits
- slow provider response times
- irrelevant cards
- duplicated dashboard behavior
- over-personalization too early

Mitigations:

- cache-first backend feed
- provider timeouts and quotas
- normalized schema
- curated provider set for v1
- strict dashboard/discover role separation

## Rollout Proposal

### Phase A

- define feed schema
- create backend aggregator endpoint
- create daily batch generation path
- launch static-curated discover page

### Phase B

- add internal relevance cards
- add dormant path and continuation cards
- improve card ranking

### Phase C

- add memory-profile-driven personalization
- adaptive ranking
- stronger Explorer handoff

## Final Recommendation

Proceed with a separate `Discover / Mainboard` page.

Keep `Dashboard` intact as the stable metrics surface.

Build Discover as:

- dynamic
- card-driven
- backend-aggregated
- cache-backed
- hybrid internal/external
- personalization-ready but not personalization-heavy on day one

This direction matches TomeHub's existing architecture and gives the product a much stronger first impression without weakening the current dashboard model.
