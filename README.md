# Content Factory
<img width="1404" height="457" alt="Görüntü" src="https://github.com/user-attachments/assets/e5b79af1-f4ed-4c86-85a8-71564a62c175" />



A brand-agnostic, multi-brand-capable autonomous AI engine for blog/SEO content.
The first (and currently only) example brand: **Oleart** (`brands/oleart/`, `knowledge/brands/oleart/`).

- Architecture: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- Development plan: [`ROADMAP.md`](./ROADMAP.md)
- Using the Knowledge Base / adding a new brand: [`knowledge/README.md`](./knowledge/README.md)
- LLM provider layer / adding a new provider: [`src/content_factory/providers/llm/README.md`](./src/content_factory/providers/llm/README.md)

## The film — 38 seconds

[![Content Factory — a 38 second film](./docs/promo/content-factory-promo.gif)](./docs/promo/content-factory-promo.mp4)

The failure that motivated the engine, the ten agents, the gate that sends drafts
backwards, and what finally ships. Built with [Remotion](https://remotion.dev) —
source in [`promo/`](./promo), 1080p mp4 in
[`docs/promo/`](./docs/promo/content-factory-promo.mp4).

## Core design decisions

- **Scope guarantee:** content can only be produced on topics declared in
  `brands/{brand}/scope.yaml`; this is enforced by two independent gates
  (deterministic + LLM classifier) rather than trusting a single prompt instruction.
- **Brand knowledge lives outside the code:** no brand name or topic appears anywhere in
  the `content_factory` package. Structured rules live in `brands/{brand}/*.yaml`,
  narrative knowledge in `knowledge/brands/{brand}/*.md`, and brand-specific prompt text
  in `brands/{brand}/prompts/`. Adding a new brand is a matter of filling in those
  directories — the core code is not touched (see [New brand / new topic](#adding-a-new-brand--new-topic)).
- **A deterministic gate against invented numbers:** `GroundingGuard` measures whether the
  unit-bearing numbers in an article (`%`, `°C`, `months`…) actually occur in the knowledge
  base. Asking an LLM "is this number correct?" was not enough — plausible-looking
  fabricated values got approved.
- **Markdown output:** the Publisher produces no HTML; it writes `content/blog/*.md` +
  `public/blog/images/`. Presentation is the target site's responsibility.
- **Git separation:** the Publisher only writes files, the `GitAgent` only commits/pushes.
- **Provider independence:** every LLM call goes through `BaseLLMProvider` (a template
  method holding cache, fallback, rate-limiting, retry and logging in one place); the
  default implementation is OpenRouter, and `config/models.yaml` can select a different
  model per agent. Adding a provider is a matter of `factory.register_provider(...)` —
  agent code does not change.
- **SQLite state:** `data/{brand}/content_factory.db` — it replaced the JSON files (see
  `ARCHITECTURE.md` §12 for the rationale), and agent code works through the `StateStore`
  interface. The schema is versioned with `PRAGMA user_version`-based migrations, so no
  data is lost.

## Adding a new brand / new topic

The engine is brand-agnostic: **which brand, which topics, which site** to publish to is
determined entirely from config. There is no need to touch Python.

The single key that selects the brand to run is the `--brand` flag
(`uv run content-factory --brand oleart`); that flag selects both of the directories below
in their entirety.

| What changes | File |
|---|---|
| **Which site it publishes to** | `brands/{brand}/publish.yaml` → `target_repo_path`, `content_dir`, `images_dir`, git remote/branch/strategy |
| **Which topics may be written about** (hard allowlist) | `brands/{brand}/scope.yaml` → `groups[].id` + `topics[]` |
| **The brand's topic knowledge** (file list, category→knowledge mapping, image scenes) | `brands/{brand}/knowledge.yaml` |
| **Narrative brand knowledge** (tone, products, FAQ, topic knowledge base) | `knowledge/brands/{brand}/*.md` |
| **Banned words/claims, word-count limits** | `brands/{brand}/brand.yaml` |
| **Keyword clusters, internal link targets** | `brands/{brand}/seo.yaml` |
| **Model/provider per agent** | `brands/{brand}/models.yaml` (deep-merged over the root `config/models.yaml`) |
| **Brand-specific prompt text** (optional) | `brands/{brand}/prompts/{agent}/system.md` |

Prompt overrides work **per file**: if the brand has its own `system.md` it is used, and if
it has no `user.md` the shared one under `prompts/` is used instead. The files in the root
`prompts/` are brand-neutral, and a test (`test_shared_prompts_are_brand_neutral`) keeps
brand and topic names from leaking into them.

For step-by-step setup and file templates: [`knowledge/README.md`](./knowledge/README.md).

## Status

**The Phase 1 core pipeline runs end to end** (397 tests) and publishes live.
All 10 agents are implemented with real business logic:

| Step | Agent | Note |
|---|---|---|
| 1 | `TopicScout` | produces candidate topics; `ScopeGuard.pre_check` + `NoveltyGuard` eliminate deterministically. Rejects are written to `topics_backlog` — **if the backlog is full this agent is never called** |
| 2 | `Research` | sourced research notes grounded in the knowledge base — the Writer's factual basis |
| 3 | `Strategist` | outline + title + keyword strategy (`Brief`) |
| 4 | `Writer` | markdown draft in the brand's voice |
| 5 | `SEOOptimizer` | meta title/description (LLM) + **deterministic** slug |
| 6 | `Linker` | no LLM; internal link plan from `StateStore` keyword overlap |
| 7 | `ImageGenerator` | one base image + 3 derivatives via Pillow (cover/thumbnail/og) |
| 8 | `Editor` | mandatory gate: deterministic rules + `GroundingGuard` (currently in warning mode) → `ScopeGuard.post_check` → LLM quality |
| 9 | `Publisher` | writes markdown with frontmatter plus images into the target repo, never touches git |
| 10 | `GitAgent` | commit/push or PR via `LocalGitProvider` |

If the Editor rejects, the Orchestrator repeats the draft loop (Writer→SEO→Linker), feeding
the reasons back as `feedback`; if `editor_reject_max_retries` is exhausted the run closes
as `needs_review` and nothing is published. Publication records (`articles`, `keywords`,
`internal_links`) are only written after the git step has succeeded.

**Status:** the pipeline is wired end to end and running in production — an article is
published automatically to oleart.co every three days (`.github/workflows/publish.yml`).
The Knowledge Base has been filled with real content and image generation is wired up: the
default provider is **Replicate** (`config/models.yaml -> agents.image_generator.provider`),
with Google AI Studio and OpenRouter as alternatives. Switching provider is a single config
field. If image generation fails the article is published without images and the pipeline
does not stop. The publishing contract on the target site is also complete
(`scripts/build-blog.mjs`).

### Quality and observability

Measuring the first published articles showed that the LLM **shifts numbers away from the
source** (the knowledge base says `5-8°C` while the article says `6-8°C`; fabrications such
as "ideal storage 14-18°C" that appear nowhere in the knowledge base). What was added in
response:

- **`GroundingGuard`** (`guards/grounding_guard.py`) — compares the unit-bearing numbers in
  an article against the numbers in the knowledge base + research notes, unit-aware; the
  Editor rejects anything ungrounded. Recipe lines ("fry at 180 °C for 8-10 minutes") and
  numbers in headings are deliberately out of scope — a false positive wastes a whole
  publishing round. Measured over 4 published articles: 4 real fabrications caught, no
  false positives. **Currently in warning mode**
  (`config/engine.yaml: grounding.enforce: false`): findings are logged but the article is
  not rejected. It will be switched to `true` once a few rounds of live accuracy have been
  measured.
- **Source verification** — the `ResearchAgent`'s `sources_used` field is matched against
  real knowledge files; file names the model invented are eliminated.
- **Research notes for the Editor** — `key_facts` is now also handed to the quality review,
  so the question "is this claim in the source?" can be asked.
- **`llm_calls` table** — every LLM call (model, tokens, duration) is written to the DB; a
  cost summary per model is logged at the end of a run.
- **Prompt contract test** — each agent's `prompt_vars` must match the `$variables` in its
  `user.md` exactly; `Template.substitute` does not stay silent on a missing variable, it
  raises.

> **Caution — image quota:** on Google AI Studio the image models (`gemini-2.5-flash-image`
> and all `*-image` variants) return `429 RESOURCE_EXHAUSTED` with `limit: 0` on the current
> key; the free quota works for text models but is **not open for images**. Until this is
> resolved articles are published without images. Alternatives: enable billing on the
> project, use `provider: replicate`, or go back to `provider: openrouter`.

### Known gaps

- **A second brand has not been tried yet.** The infrastructure is ready and verified by a
  test (`test_second_brand_works_without_touching_python`), but to date only Oleart has been
  configured — surprises may surface until a real second brand is added.
- **`examples.md` files are not sent to the model.** `PromptSet.examples` is loaded but no
  agent adds it to its prompt; few-shot examples currently have no effect.
- **`brands/{brand}/schedule.yaml` is not read.** The publishing rhythm is in practice
  determined by the cron in `.github/workflows/publish.yml`; the two must be kept in sync
  by hand.
- **`blog_url()` hard-codes the `/blog/{slug}/` shape** (`utils/text.py`) — it should be
  moved into config for a site with a different URL structure.
- The `pr-then-automerge` strategy has not been verified against a real PR (the token has no
  PR permission; `direct-push` is used for now, with the rationale in `publish.yaml`).
- The banned-phrase list in `brand.yaml` has not been through a legal review.

Detailed plan: [`ROADMAP.md`](./ROADMAP.md).

## Setup

```bash
brew install uv                 # if not installed
uv sync --extra dev
cp .env.example .env            # fill in OPENROUTER_API_KEY, REPLICATE_API_KEY/REPLICATE_API_TOKEN, GIT_TOKEN (Phase 1)

uv run pytest                   # tests
uv run ruff check src tests     # lint

uv run content-factory --brand oleart --dry-run   # writes to the target repo, does NOT commit/push
uv run content-factory --brand oleart             # full pipeline (commit + push)

# to run another brand: prepare brands/{brand}/ + knowledge/brands/{brand}/, then
uv run content-factory --brand {brand} --dry-run
```

`--dry-run` writes the generated article into the target repo but does not touch git and
does not record the publication in the `StateStore` — for inspecting the output with
`git diff` and throwing it away.
