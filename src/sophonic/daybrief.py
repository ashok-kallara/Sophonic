"""'Start my day' orchestrator — composes the daily note, Zoom, Google Tasks, and Slack.

Each source is feature-gated and error-isolated: a disabled, unauthenticated, or failing
source is recorded in the returned status and skipped, never aborting the whole brief.
Actionable items (Zoom action items, open Google Tasks, Slack DMs/@-mentions) are merged
into today's `## Tasks`; other unread Slack channels are LLM-summarized into a refreshable
`## Slack` section.
"""

from __future__ import annotations

from typing import Any


def _format_for_summary(informational: list[dict[str, Any]]) -> str:
    """Render unread channels into a compact blob for the LLM to summarize."""
    blocks: list[str] = []
    for e in informational:
        lines = [f"### {e['channel']}"]
        for m in e.get("messages", []):
            lines.append(f"{m.get('user', '')}: {m.get('text', '')}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _summarize_informational(informational: list[dict[str, Any]]) -> str:
    """LLM-summarize unread channels; fall back to deterministic counts on any failure."""
    try:
        from sophonic import llm
        md = llm.summarize(
            _format_for_summary(informational),
            instruction=(
                "These are unread Slack channels with recent messages. Write ONE concise "
                "markdown bullet per channel: what's being discussed and whether it needs my "
                "attention. Start each bullet with the channel name in bold. Bullets only."
            ),
        )
        if md.strip():
            return md.strip()
    except Exception:
        pass  # deterministic fallback below
    return "\n".join(
        f"- **{e['channel']}** — {len(e.get('messages', []))} unread" for e in informational
    )


def start_day(
    on: str | None = None,
    since: str | None = None,
    until: str | None = None,
    days: int | None = None,
    owner: str | None = None,
    dry_run: bool = False,
    skip_zoom: bool = False,
    skip_tasks: bool = False,
    skip_slack: bool = False,
) -> dict[str, Any]:
    """Build today's brief: enrich the daily note, then merge Zoom + Google Tasks + Slack.

    Zoom window options (`on`/`since`/`until`/`days`/`owner`) match `zoom.action_items`.
    `dry_run` previews without writing. `skip_*` turns off individual sources. Safe to
    re-run: task merges dedupe against today's note and the Slack section is replaced.
    """
    from sophonic.config import load_config
    from sophonic.tools import obsidian

    feat = load_config().features
    sources: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "tasks_added": {"zoom": 0, "gtasks": 0, "slack": 0},
        "slack_summary": None,
        "dry_run": dry_run,
        "sources": sources,
    }

    # 1) Ensure today's enriched note exists and carry forward yesterday's incompletes.
    try:
        note_info = obsidian.build_daily_note()
        roll = obsidian.roll_over()
        result["daily_note"] = note_info.get("file")
        result["rolled_over"] = roll.get("rolled", 0)
        sources.append({"name": "daily_note", "ok": True, "detail": f"{roll.get('rolled', 0)} rolled over"})
    except Exception as exc:  # noqa: BLE001
        sources.append({"name": "daily_note", "ok": False, "detail": str(exc)})

    # 2) Zoom meeting action items (writes + dedupes against the note itself).
    if feat.zoom and not skip_zoom:
        try:
            from sophonic.tools import zoom
            z = zoom.action_items(on=on, since=since, until=until, days=days, owner=owner, dry_run=dry_run)
            if "needs_auth" in z:
                sources.append({"name": "zoom", "ok": False, "detail": "not authenticated", "run": z.get("run")})
            elif "error" in z:
                sources.append({"name": "zoom", "ok": False, "detail": z["error"]})
            else:
                result["tasks_added"]["zoom"] = z.get("count", 0)
                sources.append({"name": "zoom", "ok": True, "detail": f"{z.get('count', 0)} action item(s)"})
        except Exception as exc:  # noqa: BLE001
            sources.append({"name": "zoom", "ok": False, "detail": str(exc)})
    elif not feat.zoom:
        sources.append({"name": "zoom", "ok": False, "detail": "disabled"})

    # Snapshot the note (after Zoom writes) for cross-source, cross-run dedupe.
    existing = [obsidian.get_daily_note()]
    seen: set[str] = set()

    def add_deduped(text: str, due=None, tags=None) -> bool:
        if text in existing[0] or text.lower() in seen:
            return False
        if not dry_run:
            obsidian.add_task(text=text, due=due, tags=tags or [])
        seen.add(text.lower())
        existing[0] += f"\n- [ ] {text}"
        return True

    # 3) Open Google Tasks → tasks (with due dates).
    if feat.google and not skip_tasks:
        try:
            from sophonic.tools import gtasks
            gt = gtasks.list_open_tasks()
            if isinstance(gt, dict):  # needs_auth / error
                entry = {"name": "gtasks", "ok": False, "detail": gt.get("detail") or gt.get("error") or "unavailable"}
                if "run" in gt:
                    entry["run"] = gt["run"]
                sources.append(entry)
            else:
                added = sum(
                    add_deduped(f"{t['title']} (Google Tasks: {t['list']})", due=t.get("due"), tags=["gtask"])
                    for t in gt
                )
                result["tasks_added"]["gtasks"] = added
                sources.append({"name": "gtasks", "ok": True, "detail": f"{added} task(s)"})
        except Exception as exc:  # noqa: BLE001
            sources.append({"name": "gtasks", "ok": False, "detail": str(exc)})
    elif not feat.google:
        sources.append({"name": "gtasks", "ok": False, "detail": "disabled"})

    # 4) Slack: DMs/@-mentions → tasks; other unread channels → summarized ## Slack section.
    if feat.slack and not skip_slack:
        try:
            from sophonic.tools import slack_local
            digest = slack_local.unread_digest()
            if "needs_auth" in digest:
                sources.append({"name": "slack", "ok": False, "detail": "not authenticated", "run": digest.get("run")})
            elif "error" in digest:
                sources.append({"name": "slack", "ok": False, "detail": digest["error"]})
            else:
                added = 0
                for e in digest.get("actionable", []):
                    if f"Reply to {e['channel']}" in existing[0]:
                        continue  # already have a reply task for this conversation
                    snippet = (e.get("latest") or "").strip().replace("\n", " ")[:80]
                    ref = f" {e['permalink']}" if e.get("permalink") else ""
                    if add_deduped(f"Reply to {e['channel']}: {snippet}{ref}".rstrip(), tags=["slack"]):
                        added += 1
                result["tasks_added"]["slack"] = added

                info = digest.get("informational", [])
                summary_md = _summarize_informational(info) if info else None
                if summary_md and not dry_run:
                    obsidian.upsert_section("Slack", summary_md)
                result["slack_summary"] = summary_md
                sources.append({
                    "name": "slack", "ok": True,
                    "detail": f"{added} reply task(s), {len(info)} channel(s) summarized",
                })
        except Exception as exc:  # noqa: BLE001
            sources.append({"name": "slack", "ok": False, "detail": str(exc)})
    elif not feat.slack:
        sources.append({"name": "slack", "ok": False, "detail": "disabled"})

    return result


TOOLS: dict[str, Any] = {
    "day_start": start_day,
}
