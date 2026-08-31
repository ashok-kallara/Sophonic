---
name: raindrop
description: >
  Turn saved Raindrop.io bookmarks into durable Obsidian reference notes under
  `<vault>/WIKI/` — one markdown file per article, with a summary, expanded context, key
  tenets, and takeaways (research papers get a plain-language rewrite). Defaults to the
  last 30 days. Use when the user asks "summarise my Raindrop bookmarks", "add my saved
  articles to Obsidian", "build wiki notes from my bookmarks", "what have I saved this
  month", or mentions turning Raindrop/bookmarks into vault notes.
---

# Raindrop → WIKI

Reads Raindrop.io through a thin fetch-script (read-only — it only lists what's saved).
*You* do everything that lands in the vault: fetch each article's actual text, write a
structured note, and file it under `<vault>/<wiki_dir>/` (default `WIKI`) per
[[obsidian]]'s conventions. The point of this skill is a note that stands in for the
source — not a link dump.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/raindrop.py" check-auth
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/raindrop.py" collections
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/raindrop.py" list --days 30
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/raindrop.py" list --since 2026-08-01 --until 2026-08-30
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/raindrop.py" list --collection Reading --limit 20
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/raindrop.py" list --tag ai --tag infra --type article
```

- `collections` — `[{id, title, path, count}]`.
- `list` — `{range:{since,until}, collection, count, truncated, items:[{id, title,
  excerpt, note, link, domain, type, tags, created, last_update, collection_id,
  important, highlights:[{text, note}]}]}`. Defaults to the last 30 days across all
  collections, newest first. `truncated: true` means a hard pagination cap was hit —
  narrow the window or a collection and re-run rather than trusting the count as complete.

## Workflow

1. **Resolve paths once.** Vault root: `$SOPHONIC_VAULT`, else
   `config.py get vault.path`. WIKI folder:
   `config.py get vault.wiki_dir` (default `WIKI`). Create
   `<vault>/<wiki_dir>/` if it doesn't exist. Below, `<wiki_dir>` means this resolved path.

2. **Fetch.** `list --days 30` unless the user named a window, collection, or tag —
   honor whatever they specified instead.

3. **Dedupe before doing any real work.** Grep `<wiki_dir>/**/*.md` for
   `^raindrop_id:` to build the set of ids already captured; drop those items from the
   list. This is a cheap check that must happen before any article fetch — mirrors
   [[meeting-recap]]'s check-before-fetch rule.

4. **Report the plan before writing anything.** State "N new, M already captured." If
   N > 40, show the count and confirm before proceeding — a 30-day pull can be large and
   this makes the cost visible first. Honor an explicit `--limit` or a request like
   "just the last 10" without asking.

5. **Pick a profile per item.** `paper` when the domain is `arxiv.org`,
   `openreview.net`, a `biorxiv.org`/`medrxiv.org` subdomain, `dl.acm.org`,
   `ieeexplore.ieee.org`, `doi.org`, or the fetched content itself reads as an academic
   preprint (abstract, sections, citations); otherwise `article`. The profile only picks
   which template file to use — the rest of the workflow is identical.

6. **Process the surviving items.**
   - **≤ 8 items:** handle them yourself, one at a time, inline.
   - **> 8 items:** split into batches of 5 and dispatch to parallel subagents (at most
     4 in flight at once). Give each subagent: the batch's item JSON, `<wiki_dir>`, and
     the **path** to `skills/raindrop/templates/article.md` or `.../paper.md` (have it
     Read the file rather than pasting the template text, so structure never drifts
     between batches). Each subagent follows steps 7-9 below for its own items and
     returns one status line per article. Batches don't share state, so if one fails or
     is interrupted, just re-run the whole skill — dedupe (step 3) skips everything
     already written.

7. **Per article — get the real text.** WebFetch `link`. For a `paper` item hosted on
   arXiv, try in this order and stop at the first success:
   - `arxiv.org/abs/<id>` — clean title/authors/abstract metadata.
   - `arxiv.org/html/<id>` then `ar5iv.labs.arxiv.org/html/<id>` — full HTML body; far
     more reliable to fetch and parse than the PDF. Normalize a `/pdf/<id>` link to
     `/abs/<id>` first.

   If the fetch fails (paywall, JS-only page, 404, timeout), fall back to the item's
   `excerpt` + `note` + `highlights` and set `fetch_status: excerpt-only`. If there's
   truly nothing usable, still write the note — title, url, and frontmatter only, plus a
   one-line `## Summary` saying the fetch failed — with `fetch_status: failed`, so the
   bookmark is recorded and a later run can retry just that one. **Never let one bad
   article abort the batch.**

8. **Write the note.** Read the template (see step 6) and follow it exactly — see
   "Note structure" below for the rules governing it. Path:
   `<wiki_dir>/<Sanitized Title>.md`. Sanitize the title for the filename: strip
   `/ \ : * ? " < > | # ^ [ ]`, collapse whitespace, trim to 90 chars; if that leaves
   nothing, use `<domain> <id>`. If a file at that path already exists with a
   *different* `raindrop_id`, disambiguate — append ` (<domain>)`, then ` (<id>)` if
   still colliding. Never overwrite a note that isn't this bookmark.

9. **Regeneration.** If the user asks to refresh an existing note, Read it first and
   carry its entire `## My Notes` section through byte-for-byte into the rewritten file.

10. **Update the index (idempotent).** Under
    `<wiki_dir>/WIKI Index.md`, add
    `- [[<Title>]] — <TL;DR> · <domain> · <bookmarked date>` under a `## <YYYY-MM>`
    heading (create the file/heading if absent). Dedupe on the wikilink text — skip if
    already present.

11. **Report.** Counts created / skipped(already captured) / excerpt-only / failed,
    split by profile (article vs paper). List each failure with its reason and the
    exact `list` command to retry just the gaps.

## Note structure

Every note — main session or subagent — follows the same rules:

1. **Progressive disclosure.** Order is TL;DR → Summary → Context/Problem → Details →
   Key Tenets/How It Works → Takeaways → Caveats/Limitations. A reader should get value
   at 10 seconds, 1 minute, and 10 minutes in.
2. **Source and expansion never mix.** `## Summary`, `## Details`/`## Results`, and
   `## Highlights` carry *only* what the source said. Anything Claude adds — background,
   definitions, implications — goes only in the sections explicitly marked as expansion
   (`## Context`, `## Jargon Decoder`, `## Key Tenets & Traits`, `## Takeaways`). This is
   what keeps the WIKI trustworthy months later.
3. **Section headings are fixed.** Never rename or reorder them. Omit a section only
   when it is genuinely empty (e.g. no highlights) — don't leave placeholder text.
4. **Set `aliases:`** in frontmatter — acronyms, short names, author-year — so wikilinks
   resolve however the user later refers to it.
5. **Length discipline.** ~400-700 words for an article note, ~700-1200 for a paper
   note. Long enough to stand in for the source, short enough to reread.

### Simplification contract for papers

Assume the reader knows general data science — regression, train/test splits, gradient
descent, overfitting, basic probability, numpy/pandas — and assume they know **none** of
this paper's subfield jargon. Expand every acronym on first use. Prefer a concrete
number or worked example to notation. Only keep an equation if it carries real meaning,
and gloss it in words immediately after. Never simplify to the point of changing what
the paper actually claims — when plain language and precision pull apart, give the plain
version first and the precise version right after it.

## Auth

If any call returns `{"needs_auth": true}`, tell the user to create a token at
raindrop.io → Settings → Integrations → **+ Create new app** → **Create test token**,
then run **in their own terminal**:
`uv run python scripts/config.py set-secret RAINDROP_TOKEN --stdin`. Also needs
`features.raindrop true` (`scripts/config.py set features.raindrop true`). Never type the
token into a tool call yourself. Setup: [[setup]].

A `{"error": ...}` from `collections`/`list` naming an unrecognized collection includes
`available` — the real collection paths — offer those back to the user.

Related: [[obsidian]], [[setup]], [[ask]].
