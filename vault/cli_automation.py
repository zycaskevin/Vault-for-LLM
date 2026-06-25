"""Automation CLI command handler and parser registration."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable


def cmd_automation(
    args: argparse.Namespace,
    *,
    find_project_dir: Callable[[], Any],
    json_print: Callable[..., None],
) -> None:
    """Policy-based memory automation workflows."""
    from vault.automation import (
        automation_activity,
        automation_brief,
        automation_cycle,
        automation_doctor,
        automation_eval,
        automation_fleet_health,
        automation_handoff,
        automation_inbox,
        automation_learning_health,
        automation_plan,
        automation_report,
        automation_review_feedback,
        automation_review_summary,
        automation_run,
    )

    action = getattr(args, "automation_action", "")
    if action not in {"plan", "run", "cycle", "report", "activity", "brief", "review-summary", "review-feedback", "learning-health", "fleet-health", "inbox", "handoff", "doctor", "eval"}:
        print(
            "error: automation requires action: plan, run, cycle, report, activity, brief, review-summary, review-feedback, learning-health, fleet-health, inbox, handoff, eval, or doctor",
            file=sys.stderr,
        )
        raise SystemExit(2)

    project_dir = find_project_dir()
    try:
        if action == "plan":
            payload = automation_plan(
                project_dir,
                mode=args.mode,
                limit=args.limit,
                write_policy_file=args.write_policy,
                overwrite_policy=args.overwrite_policy,
            )
        elif action == "run":
            payload = automation_run(
                project_dir,
                mode=args.mode,
                apply=args.apply,
                limit=args.limit,
                write_reports=not args.no_report,
            )
        elif action == "cycle":
            payload = automation_cycle(
                project_dir,
                mode=args.mode,
                apply=args.apply,
                limit=args.limit,
                min_events=args.min_events,
                write_reports=not args.no_report,
                write_workspace=getattr(args, "write_workspace", False),
                workspace_path=getattr(args, "workspace_path", ""),
                inbox_limit=getattr(args, "inbox_limit", 5),
                include_transcripts=getattr(args, "include_transcripts", False),
                transcript_limit=getattr(args, "transcript_limit", 5),
                capture_transcripts=getattr(args, "capture_transcripts", False),
                capture_transcript_limit=getattr(args, "capture_transcript_limit", 3),
                capture_max_candidates_per_transcript=getattr(args, "capture_max_candidates_per_transcript", 5),
                capture_min_score=getattr(args, "capture_min_score", 0.55),
            )
        elif action == "report":
            payload = automation_report(
                project_dir,
                limit=args.limit,
                latest=args.latest,
                detail=args.detail,
                report_path=args.report_path,
            )
        elif action == "activity":
            payload = automation_activity(
                project_dir,
                limit=args.limit,
                event_limit=getattr(args, "event_limit", 20),
            )
        elif action == "brief":
            payload = automation_brief(
                project_dir,
                limit=args.limit,
                review_limit=getattr(args, "review_limit", 5),
                min_events=getattr(args, "min_events", 5),
                write_brief=getattr(args, "write_brief", False),
                brief_path=getattr(args, "brief_path", ""),
            )
        elif action == "review-summary":
            payload = automation_review_summary(
                project_dir,
                limit=args.limit,
                min_events=getattr(args, "min_events", 5),
                write_summary=getattr(args, "write_summary", False),
                summary_path=getattr(args, "summary_path", ""),
            )
        elif action == "review-feedback":
            payload = automation_review_feedback(
                project_dir,
                card_kind=getattr(args, "kind", ""),
                card_id=getattr(args, "card_id", ""),
                decision=getattr(args, "decision", ""),
                reason=getattr(args, "reason", ""),
                recommended_action=getattr(args, "recommended_action", ""),
                score=getattr(args, "score", None),
                summary_path=getattr(args, "summary_path", ""),
                min_events=getattr(args, "min_events", 5),
                write_learning_policy=getattr(args, "write_learning_policy", False),
            )
        elif action == "learning-health":
            payload = automation_learning_health(
                project_dir,
                limit=args.limit,
                min_events=getattr(args, "min_events", 5),
                write_health=getattr(args, "write_health", False),
                health_path=getattr(args, "health_path", ""),
            )
        elif action == "fleet-health":
            payload = automation_fleet_health(
                project_dir,
                limit=args.limit,
                min_events=getattr(args, "min_events", 5),
                max_status_age_minutes=getattr(args, "max_status_age_minutes", 24 * 60),
                write_health=getattr(args, "write_health", False),
                health_path=getattr(args, "health_path", ""),
            )
        elif action == "inbox":
            payload = automation_inbox(
                project_dir,
                limit=args.limit,
                include_content=getattr(args, "include_content", False),
                include_transcripts=getattr(args, "include_transcripts", False),
                transcript_limit=getattr(args, "transcript_limit", 5),
                write_handoff=getattr(args, "write_handoff", False),
                handoff_path=getattr(args, "handoff_path", ""),
            )
        elif action == "handoff":
            payload = automation_handoff(
                project_dir,
                source=getattr(args, "source", "auto"),
                handoff_path=getattr(args, "handoff_path", ""),
            )
        elif action == "eval":
            payload = automation_eval(
                project_dir,
                limit=args.limit,
                min_events=args.min_events,
                write_learning_policy=getattr(args, "write_learning_policy", False),
            )
        else:
            payload = automation_doctor(project_dir, mode=args.mode)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.json or args.pretty:
        json_print(payload, pretty=args.pretty)
        return

    def _print_usage_review(payload):
        review = payload.get("usage_review") or {}
        suggestions = review.get("suggestions") or []
        if not suggestions:
            return
        print("\n  Usage review:")
        for item in suggestions:
            print(f"    - {item.get('kind')}: {item.get('count')} [{item.get('autonomy')}]")

    if action == "plan":
        print("🧭 Automation plan\n")
        print(f"  mode: {payload.get('mode')}")
        print(f"  policy: {payload.get('policy_path') or '(not written)'}")
        print(f"  candidates: {payload.get('candidate_count', 0)}")
        usage = payload.get("usage", {})
        print(f"  expired active: {usage.get('expired_active_count', 0)}")
        _print_usage_review(payload)
        print("\n  Planned actions:")
        for item in payload.get("planned_actions", []):
            enabled = item.get("enabled")
            suffix = "" if enabled is None else f" enabled={enabled}"
            print(f"    - {item.get('id')} [{item.get('autonomy')}]{suffix}")
        if payload.get("human_review", {}).get("required"):
            print("\n  Human review suggested for:")
            for item in payload["human_review"].get("items", []):
                print(f"    - {item.get('kind')}: {item.get('count')}")
        return

    if action == "run":
        print("🤖 Automation run\n")
        print(f"  status: {payload.get('status')}")
        print(f"  mode: {payload.get('mode')}")
        print(f"  apply: {payload.get('apply')}")
        print(f"  report: {payload.get('report_path', '')}")
        print(
            f"  candidates: before={payload.get('candidate_count_before', payload.get('candidate_count', 0))} "
            f"after={payload.get('candidate_count_after', payload.get('candidate_count', 0))}"
        )
        archive = payload.get("archive_expired", {})
        print(
            f"  archive expired: eligible={archive.get('eligible_count', 0)} "
            f"archived={archive.get('archived_count', 0)} "
            f"skipped_used={archive.get('skipped_used_count', 0)} "
            f"skipped_policy={archive.get('skipped_protected_count', 0)} "
            f"dry_run={archive.get('dry_run')}"
        )
        cold_store = payload.get("cold_store_expired", {})
        print(
            f"  cold-store expired: eligible={cold_store.get('eligible_count', 0)} "
            f"applied={cold_store.get('applied_count', 0)} "
            f"skipped_usage={cold_store.get('skipped_low_usage_count', 0)} "
            f"skipped_policy={cold_store.get('skipped_protected_count', 0)} "
            f"dry_run={cold_store.get('dry_run')}"
        )
        diff = payload.get("dry_run_diff") or {}
        if diff:
            print(
                f"  diff: would_archive={diff.get('would_archive_count', 0)} "
                f"applied={diff.get('applied_count', 0)} "
                f"would_cold_store={diff.get('would_cold_store_count', 0)} "
                f"cold_stored={diff.get('cold_store_applied_count', 0)} "
                f"policy_skips={diff.get('skipped_policy_count', 0)} "
                f"hard_delete={diff.get('hard_delete')}"
            )
        _print_usage_review(payload)
        ledger = payload.get("action_ledger") or []
        if ledger:
            print("  action ledger:")
            for item in ledger[:5]:
                print(
                    f"    - #{item.get('knowledge_id')} {item.get('operation')} "
                    f"{item.get('status')} ({item.get('reason')})"
                )
            if len(ledger) > 5:
                print(f"    ... {len(ledger) - 5} more")
        dream = payload.get("dream", {})
        print(f"  dream report: {dream.get('report_path', '')}")
        dream_summary = dream.get("summary") or {}
        if dream_summary:
            print(
                "  dream candidates: "
                f"suggested={dream_summary.get('candidate_suggestions', 0)} "
                f"written={dream_summary.get('candidates_written', 0)} "
                f"skipped_existing={dream_summary.get('candidates_skipped_existing', 0)}"
            )
        forgetting = payload.get("forgetting") or {}
        if forgetting:
            print(
                "  forgetting candidates: "
                f"suggested={forgetting.get('candidate_suggestions', 0)} "
                f"written={forgetting.get('candidates_written', 0)} "
                f"skipped_existing={forgetting.get('candidates_skipped_existing', 0)}"
            )
        auto_promote = payload.get("auto_promote") or {}
        if auto_promote:
            print(
                "  auto-promote: "
                f"enabled={auto_promote.get('enabled', False)} "
                f"would={auto_promote.get('would_promote_count', 0)} "
                f"promoted={auto_promote.get('promoted_count', 0)} "
                f"skipped={auto_promote.get('skipped_count', 0)}"
            )
        if payload.get("human_review", {}).get("required"):
            print("  review: required")
        return

    if action == "cycle":
        summary = payload.get("summary") or {}
        print("🔁 Automation cycle\n")
        print(f"  status: {payload.get('status')}")
        print(f"  mode: {payload.get('mode') or args.mode or '(policy)'}")
        print(f"  apply: {payload.get('apply')}")
        print(f"  feedback events: {summary.get('feedback_events', 0)}")
        print(f"  learning rules: {summary.get('learning_rules', 0)}")
        print(f"  learning policy: {summary.get('learning_policy_path') or '(not written)'}")
        print(
            "  dream learning: "
            f"{summary.get('dream_learning_policy_status') or '(none)'} "
            f"rules={summary.get('dream_learning_policy_applied_rules', 0)}"
        )
        print(
            "  candidates: "
            f"before={summary.get('candidate_count_before', 0)} "
            f"after={summary.get('candidate_count_after', 0)} "
            f"written={summary.get('candidates_written', 0)}"
        )
        capture = payload.get("transcript_capture") or {}
        capture_summary = capture.get("summary") or {}
        if capture:
            print(
                "  transcript capture: "
                f"status={capture.get('status', '')} "
                f"seen={capture_summary.get('transcripts_seen', 0)} "
                f"captured={capture_summary.get('transcripts_captured', 0)} "
                f"candidates_written={capture_summary.get('candidates_written', 0)}"
            )
        if summary.get("automation_report_path"):
            print(f"  report: {summary.get('automation_report_path')}")
        if payload.get("workspace_path"):
            workspace = payload.get("workspace") or {}
            workspace_summary = workspace.get("summary") or {}
            print(f"  workspace: {payload.get('workspace_path')}")
            if payload.get("workspace_markdown_path"):
                print(f"  workspace markdown: {payload.get('workspace_markdown_path')}")
            print(
                "  workspace queue: "
                f"candidates={workspace_summary.get('candidate_queue_items', 0)} "
                f"needs_review={workspace_summary.get('needs_review', 0)} "
                f"uncaptured_transcripts={workspace_summary.get('uncaptured_transcripts', 0)}"
            )
        if payload.get("human_review", {}).get("required"):
            print("\n  Human review required for:")
            for item in payload["human_review"].get("items", []):
                print(f"    - {item.get('kind')}: {item.get('count')}")
        print(f"\n  principle: {payload.get('principle')}")
        return

    if action == "handoff":
        fleet_content = (payload.get("fleet_health_content") or "").rstrip()
        review_content = (payload.get("review_summary_content") or "").rstrip()
        learning_content = (payload.get("learning_health_content") or "").rstrip()
        if payload.get("status") != "completed":
            print("📄 Automation handoff\n")
            print(f"  status: {payload.get('status')}")
            print(f"  source: {payload.get('source')}")
            for content in (fleet_content, review_content, learning_content):
                if content:
                    print("\n---\n")
                    print(content)
            print(f"  next action: {payload.get('next_action')}")
            return
        if payload.get("content_type") == "markdown":
            for content in (fleet_content, review_content, learning_content):
                if content:
                    print(content)
                    print("\n---\n")
            print(payload.get("content", "").rstrip())
            return
        print("📄 Automation handoff\n")
        print(f"  path: {payload.get('handoff_path')}")
        print(f"  type: {payload.get('content_type')}")
        if payload.get("fleet_health_path"):
            print(f"  fleet health: {payload.get('fleet_health_path')}")
        if payload.get("review_summary_path"):
            print(f"  review summary: {payload.get('review_summary_path')}")
        if payload.get("learning_health_path"):
            print(f"  learning health: {payload.get('learning_health_path')}")
        print(payload.get("content", "").rstrip())
        return

    if action == "report":
        print("📋 Automation reports\n")
        if payload.get("report"):
            item = payload.get("report", {})
            review = "review" if item.get("human_review", {}).get("required") else "ok"
            print(f"  {item.get('path')} mode={item.get('mode')} status={item.get('status')} {review}")
            print(
                f"  archive: eligible={item.get('eligible_count', 0)} "
                f"archived={item.get('archived_count', 0)} "
                f"skipped_used={item.get('skipped_used_count', 0)} "
                f"skipped_policy={item.get('skipped_policy_count', 0)}"
            )
            print(
                f"  cold-store: eligible={item.get('cold_store_eligible_count', 0)} "
                f"applied={item.get('cold_store_applied_count', 0)} "
                f"skipped_policy={item.get('cold_store_skipped_protected_count', 0)}"
            )
            diff = item.get("dry_run_diff") or {}
            print(
                f"  diff: would_archive={diff.get('would_archive_count', 0)} "
                f"applied={diff.get('applied_count', 0)} "
                f"would_cold_store={diff.get('would_cold_store_count', 0)} "
                f"cold_stored={diff.get('cold_store_applied_count', 0)} "
                f"hard_delete={diff.get('hard_delete')} "
                f"permission_changes={diff.get('permission_changes')}"
            )
            print(f"  ledger entries: {item.get('ledger_count', 0)}")
            print(
                f"  dream candidates: suggested={item.get('dream_candidate_suggestions', 0)} "
                f"written={item.get('dream_candidates_written', 0)} "
                f"skipped_existing={item.get('dream_candidates_skipped_existing', 0)}"
            )
            print(
                f"  forgetting candidates: suggested={item.get('forgetting_candidate_suggestions', 0)} "
                f"written={item.get('forgetting_candidates_written', 0)} "
                f"skipped_existing={item.get('forgetting_candidates_skipped_existing', 0)}"
            )
            print(
                f"  auto-promote: enabled={item.get('auto_promote_enabled', False)} "
                f"would={item.get('auto_promote_would_promote_count', 0)} "
                f"promoted={item.get('auto_promote_promoted_count', 0)}"
            )
            detail = payload.get("detail") or {}
            ledger = detail.get("action_ledger") or []
            if ledger:
                print("  action ledger:")
                for entry in ledger[: args.limit]:
                    print(
                        f"    - #{entry.get('knowledge_id')} {entry.get('operation')} "
                        f"{entry.get('status')} ({entry.get('reason')})"
                    )
                if len(ledger) > args.limit:
                    print(f"    ... {len(ledger) - args.limit} more")
            return
        for item in payload.get("reports", []):
            review = "review" if item.get("human_review", {}).get("required") else "ok"
            print(f"  {item.get('path')} mode={item.get('mode')} status={item.get('status')} {review}")
        return

    if action == "activity":
        totals = payload.get("totals") or {}
        print("📡 Automation activity\n")
        print(f"  status: {payload.get('status')}")
        print(f"  reports: {payload.get('report_count', 0)}")
        print(
            "  auto-promote: "
            f"enabled_runs={totals.get('auto_promote_enabled_runs', 0)} "
            f"would={totals.get('would_promote_count', 0)} "
            f"promoted={totals.get('promoted_count', 0)} "
            f"skipped={totals.get('skipped_count', 0)}"
        )
        print(
            "  archive: "
            f"applied={totals.get('archive_applied_count', 0)} "
            f"skipped={totals.get('archive_skipped_count', 0)}"
        )
        print(
            "  cold-store: "
            f"preview={totals.get('cold_store_preview_count', 0)} "
            f"applied={totals.get('cold_store_applied_count', 0)} "
            f"skipped={totals.get('cold_store_skipped_count', 0)}"
        )
        events = payload.get("events") or []
        if events:
            print("  events:")
            for item in events[: args.event_limit]:
                subject = item.get("candidate_id") or item.get("knowledge_id") or ""
                print(
                    f"    - {item.get('kind')} {subject} "
                    f"reason={item.get('reason', '')}"
                )
        return

    if action == "brief":
        summary = payload.get("summary") or {}
        review = payload.get("human_review_5_percent") or {}
        forgetting = payload.get("forgetting_strategy") or {}
        learning = payload.get("learning") or {}
        weights = payload.get("memory_weights") or {}
        agent_health = payload.get("agent_health") or {}
        print("🧠 Automation intelligence brief\n")
        print(f"  status: {payload.get('status')}")
        print(
            "  review: "
            f"pending={summary.get('pending_candidates', 0)} "
            f"needs_review={summary.get('needs_review', 0)} "
            f"shown={len(review.get('items') or [])}/{review.get('budget', 0)}"
        )
        print(
            "  learning: "
            f"readiness={learning.get('readiness') or summary.get('learning_readiness', '')} "
            f"events={learning.get('event_count', 0)} "
            f"rules={len(learning.get('top_rules') or [])}"
        )
        print(
            "  weights: "
            f"top_used={len(weights.get('top_used') or [])} "
            f"accesses={weights.get('total_accesses', 0)} "
            f"citations={weights.get('total_citations', 0)}"
        )
        print(
            "  forgetting: "
            f"expired={forgetting.get('expired_active_count', 0)} "
            f"archiveable={forgetting.get('archiveable_count', 0)} "
            f"used_expired={forgetting.get('used_expired_count', 0)} "
            f"protected={forgetting.get('protected_expired_count', 0)}"
        )
        print(
            "  cold-store: "
            f"preview={summary.get('cold_store_preview', 0)} "
            f"applied={summary.get('cold_store_applied', 0)}"
        )
        print(f"  agent health: registered={agent_health.get('agent_count', 0)}")
        if payload.get("brief_path"):
            print(f"  brief: {payload.get('brief_path')}")
        if payload.get("brief_markdown_path"):
            print(f"  brief markdown: {payload.get('brief_markdown_path')}")
        items = review.get("items") or []
        if items:
            print("\n  Human review 5%:")
            for item in items:
                print(
                    f"    - {item.get('kind')} {item.get('id')} "
                    f"action={item.get('recommended_action')} reason={item.get('reason')}"
                )
        else:
            print("\n  Human review 5%: empty")
        return

    if action == "review-summary":
        summary = payload.get("summary") or {}
        cards = payload.get("cards") or []
        print("✅ Automation review summary\n")
        print(f"  status: {payload.get('status')}")
        print(
            "  review: "
            f"cards={summary.get('cards', 0)} "
            f"requires_human_decision={summary.get('requires_human_decision', False)} "
            f"top_importance={summary.get('top_importance_score', 0)}"
        )
        print(
            "  queue: "
            f"pending={summary.get('pending_candidates', 0)} "
            f"needs_review={summary.get('needs_review', 0)} "
            f"expired={summary.get('expired_active', 0)} "
            f"cold_store_preview={summary.get('cold_store_preview', 0)}"
        )
        if payload.get("review_summary_path"):
            print(f"  summary: {payload.get('review_summary_path')}")
        if payload.get("review_summary_markdown_path"):
            print(f"  summary markdown: {payload.get('review_summary_markdown_path')}")
        if cards:
            print("\n  Review cards:")
            for card in cards:
                print(
                    f"    - P{card.get('priority', 0)} {card.get('kind')} "
                    f"{card.get('id')} action={card.get('recommended_action')}"
                )
                print(f"      {card.get('title')}")
                print(f"      why: {card.get('reason')}")
                print(f"      safe: {card.get('safe_action')}")
        else:
            print("\n  Review cards: empty")
        return

    if action == "review-feedback":
        print("✅ Automation review feedback\n")
        print(f"  status: {payload.get('status')}")
        print(f"  event_id: {payload.get('event_id', '')}")
        card = payload.get("card") or {}
        feedback = payload.get("feedback") or {}
        learning = payload.get("learning") or {}
        print(
            "  card: "
            f"kind={card.get('kind', '')} "
            f"id={card.get('id', '')} "
            f"found={card.get('found_in_summary', False)}"
        )
        if card.get("title"):
            print(f"  title: {card.get('title')}")
        print(
            "  feedback: "
            f"decision={feedback.get('decision', '')} "
            f"outcome={feedback.get('outcome', '')} "
            f"score={feedback.get('score', 0)}"
        )
        print(f"  reason: {feedback.get('reason', '')}")
        print(
            "  learning: "
            f"readiness={learning.get('readiness', '')} "
            f"events={learning.get('event_count', 0)}"
        )
        if learning.get("learning_policy_path"):
            print(f"  learning policy written: {learning.get('learning_policy_path')}")
        closed_loop = payload.get("closed_loop") or {}
        if closed_loop.get("review_summary_path"):
            print(f"  next review summary: {closed_loop.get('review_summary_path')}")
        if closed_loop.get("learning_health_path"):
            print(f"  learning health: {closed_loop.get('learning_health_path')}")
        if closed_loop.get("top_learning_action"):
            print(f"  learned action: {closed_loop.get('top_learning_action')}")
        print("  safety: feedback-only; no memory promotion, archive, or delete")
        return

    if action == "learning-health":
        summary = payload.get("summary") or {}
        print("📊 Automation learning health\n")
        print(f"  status: {payload.get('status')}")
        print(
            "  summary: "
            f"readiness={summary.get('readiness', '')} "
            f"events={summary.get('event_count', 0)} "
            f"positive_rate={summary.get('positive_rate', 0)}"
        )
        print(
            "  rules: "
            f"prefer={summary.get('prefer_rules', 0)} "
            f"downgrade={summary.get('downgrade_rules', 0)} "
            f"observe={summary.get('observe_rules', 0)}"
        )
        if payload.get("health_path"):
            print(f"  health: {payload.get('health_path')}")
        if payload.get("health_markdown_path"):
            print(f"  health markdown: {payload.get('health_markdown_path')}")
        cards = payload.get("cards") or []
        if cards:
            print("\n  Health cards:")
            for card in cards:
                print(f"    - P{card.get('priority', 0)} {card.get('kind')} {card.get('title')}")
                print(f"      why: {card.get('reason')}")
                print(f"      safe: {card.get('safe_action')}")
        else:
            print("\n  Health cards: empty")
        return

    if action == "fleet-health":
        summary = payload.get("summary") or {}
        print("🛰️ Automation fleet health\n")
        print(f"  status: {payload.get('status')}")
        print(
            "  agents: "
            f"registered={summary.get('registered_agents', 0)} "
            f"project={summary.get('agents_for_project', 0)}"
        )
        print(
            "  learning: "
            f"status={summary.get('learning_status', '')} "
            f"readiness={summary.get('learning_readiness', '')} "
            f"events={summary.get('learning_events', 0)} "
            f"rules={summary.get('learning_rules', 0)}"
        )
        print(
            "  update: "
            f"exists={summary.get('update_status_exists', False)} "
            f"ok={summary.get('update_distribution_ok', False)} "
            f"attention={summary.get('agents_needing_attention', 0)} "
            f"missing={summary.get('agents_missing_from_status', 0)}"
        )
        if payload.get("fleet_health_path"):
            print(f"  fleet health: {payload.get('fleet_health_path')}")
        if payload.get("fleet_health_markdown_path"):
            print(f"  fleet health markdown: {payload.get('fleet_health_markdown_path')}")
        cards = payload.get("cards") or []
        if cards:
            print("\n  Fleet cards:")
            for card in cards:
                print(f"    - P{card.get('priority', 0)} {card.get('kind')} {card.get('title')}")
                print(f"      why: {card.get('reason')}")
                print(f"      safe: {card.get('safe_action')}")
        else:
            print("\n  Fleet cards: empty")
        return

    if action == "inbox":
        summary = payload.get("summary") or {}
        print("📥 Automation inbox\n")
        print(f"  status: {payload.get('status')}")
        print(
            "  candidates: "
            f"pending={summary.get('pending_candidates', 0)} "
            f"rejected={summary.get('rejected_candidates', 0)} "
            f"privacy_blocked={summary.get('privacy_blocked', 0)} "
            f"needs_review={summary.get('needs_review', 0)}"
        )
        print(
            "  gates: "
            f"duplicate_review={summary.get('duplicate_review', 0)} "
            f"quality_review={summary.get('quality_review', 0)}"
        )
        print(
            "  transcripts: "
            f"uncaptured={summary.get('uncaptured_transcripts', 0)} "
            f"read_contents={summary.get('transcript_discovery_reads_contents', False)}"
        )
        if summary.get("latest_report_path"):
            review = "review" if summary.get("latest_report_review_required") else "ok"
            print(f"  latest report: {summary.get('latest_report_path')} {review}")
        learning = payload.get("learning_policy") or {}
        if learning:
            print(
                "  learning policy: "
                f"{learning.get('status', 'missing')} "
                f"rules_applied={learning.get('applied_rules', 0)}"
            )
        if payload.get("inbox_handoff_path"):
            print(f"  inbox handoff: {payload.get('inbox_handoff_path')}")
        digest = payload.get("review_digest") or {}
        digest_items = digest.get("items") or []
        if digest_items:
            print("\n  Review digest:")
            for item in digest_items:
                label = item.get("id") or item.get("kind") or "review"
                count = item.get("count", 1)
                print(
                    f"    - {label} priority={item.get('priority', 0)} "
                    f"count={count} action={item.get('recommended_action')}"
                )
                print(f"      {item.get('title')}")
                print(f"      safe: {item.get('safe_action')}")
                if item.get("learning_action"):
                    print(
                        f"      learning: {item.get('learning_action')} "
                        f"x{item.get('learning_multiplier', 1.0)}"
                    )
        queue = payload.get("review_queue") or []
        if queue:
            print("\n  Review queue:")
            for item in queue:
                print(
                    f"    - {item.get('id')} priority={item.get('priority')} "
                    f"action={item.get('recommended_action')} "
                    f"source={item.get('source') or '(none)'} "
                    f"type={item.get('memory_type') or '(none)'}"
                )
                print(f"      {item.get('title')}")
                print(f"      reason: {item.get('reason')}")
        else:
            print("\n  Review queue: empty")
        transcripts = (payload.get("transcript_discovery") or {}).get("transcripts") or []
        if transcripts:
            print("\n  Transcript candidates:")
            for item in transcripts[: args.limit]:
                print(
                    f"    - {item.get('capture_path')} "
                    f"source={item.get('source_system')} "
                    f"format={item.get('format')} "
                    f"score={item.get('score')}"
                )
        print(f"\n  principle: {summary.get('principle')}")
        return

    if action == "eval":
        print("📈 Automation eval\n")
        print(f"  status: {payload.get('status')}")
        print(f"  readiness: {payload.get('readiness')}")
        print(f"  feedback events: {payload.get('event_count', 0)}")
        print(f"  outcomes: {payload.get('outcome_counts', {})}")
        pending = payload.get("pending_candidates") or {}
        print(f"  pending candidates: {pending.get('count', 0)}")
        groups = payload.get("source_memory_type_scores") or []
        if groups:
            print("  source/type scores:")
            for item in groups[: args.limit]:
                print(
                    f"    - source={item.get('source') or '(none)'} "
                    f"type={item.get('memory_type') or '(none)'} "
                    f"category={item.get('category') or '(none)'} "
                    f"total={item.get('total', 0)} "
                    f"acceptance={item.get('acceptance_rate', 0):.2f} "
                    f"recommendation={item.get('recommendation')}"
                )
        learning = payload.get("learning_policy") or {}
        rules = learning.get("rules") or []
        if rules:
            print("  learning policy:")
            for item in rules[: args.limit]:
                selector = item.get("selector") or {}
                print(
                    f"    - source={selector.get('source') or '(none)'} "
                    f"type={selector.get('memory_type') or '(none)'} "
                    f"category={selector.get('category') or '(none)'} "
                    f"action={item.get('action')} "
                    f"multiplier={item.get('priority_multiplier')} "
                    f"confidence={item.get('confidence')}"
                )
        if payload.get("learning_policy_path"):
            print(f"  learning policy written: {payload.get('learning_policy_path')}")
        return

    print("🩺 Automation doctor\n")
    print(f"  ok: {payload.get('ok')}")
    for item in payload.get("checks", []):
        icon = "✅" if item.get("ok") else "❌"
        print(f"  {icon} {item.get('name')}: {item.get('detail')}")


def add_automation_parser(sub: argparse._SubParsersAction) -> None:
    # automation — policy-based memory maintenance
    p = sub.add_parser("automation", help="Policy-based memory automation workflows")
    automation_sub = p.add_subparsers(dest="automation_action", help="Automation 子命令")

    def add_automation_common(sp):
        sp.add_argument("--mode", choices=["conservative", "balanced", "autonomous"],
                        help="override automation policy mode")
        sp.add_argument("--limit", "-n", type=int, default=50)
        sp.add_argument("--json", action="store_true", help="輸出 JSON")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    sp = automation_sub.add_parser("plan", help="Preview maintenance actions and review pressure")
    add_automation_common(sp)
    sp.add_argument("--write-policy", action="store_true", help="write automation_policy.yaml if missing")
    sp.add_argument("--overwrite-policy", action="store_true", help="overwrite automation_policy.yaml")

    sp = automation_sub.add_parser("run", help="Run report-first automation; --apply only performs policy-allowed reversible actions")
    add_automation_common(sp)
    sp.add_argument("--apply", action="store_true", help="apply policy-allowed reversible actions")
    sp.add_argument("--no-report", action="store_true", help="do not write reports/automation JSON or dream report")

    sp = automation_sub.add_parser("cycle", help="Evaluate feedback, write learning policy, then run safe automation")
    add_automation_common(sp)
    sp.add_argument("--apply", action="store_true", help="apply policy-allowed reversible actions")
    sp.add_argument("--no-report", action="store_true", help="do not write reports/automation JSON or dream report")
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before a group is considered learnable")
    sp.add_argument("--write-workspace", action="store_true", help="write reports/automation/cycle-latest.json as a compact cycle handoff")
    sp.add_argument("--workspace-path", default="", help="custom reports/automation/*.json cycle workspace path")
    sp.add_argument("--inbox-limit", type=int, default=5, help="maximum review queue items in the cycle workspace")
    sp.add_argument("--include-transcripts", action="store_true", help="include metadata-only transcript discovery hints in the cycle workspace")
    sp.add_argument("--transcript-limit", type=int, default=5, help="maximum transcript discovery hints in the cycle workspace")
    sp.add_argument("--capture-transcripts", action="store_true", help="with --apply, convert discovered transcripts into review candidates; never promotes")
    sp.add_argument("--capture-transcript-limit", type=int, default=3, help="maximum transcripts to capture into candidates")
    sp.add_argument("--capture-max-candidates-per-transcript", type=int, default=5, help="maximum candidates written per captured transcript")
    sp.add_argument("--capture-min-score", type=float, default=0.55, help="minimum deterministic capture score")

    sp = automation_sub.add_parser("report", help="List recent automation reports")
    add_automation_common(sp)
    sp.add_argument("--latest", action="store_true", help="show the latest automation report summary")
    sp.add_argument("--detail", action="store_true", help="include full report detail and ledger")
    sp.add_argument("--report-path", default="", help="read a specific reports/automation/*.json file")

    sp = automation_sub.add_parser("activity", help="Show compact closed-loop automation activity")
    add_automation_common(sp)
    sp.add_argument("--event-limit", type=int, default=20, help="maximum activity events to show")

    sp = automation_sub.add_parser("brief", help="Show a compact automation intelligence brief")
    add_automation_common(sp)
    sp.add_argument("--review-limit", type=int, default=5, help="maximum human-review items to show")
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before a group is considered learnable")
    sp.add_argument("--write-brief", action="store_true", help="write reports/automation/brief-latest.json and .md")
    sp.add_argument("--brief-path", default="", help="custom reports/automation/*.json brief path")

    sp = automation_sub.add_parser("review-summary", help="Show the shortest human approval cards for automation")
    add_automation_common(sp)
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before a group is considered learnable")
    sp.add_argument("--write-summary", action="store_true", help="write reports/automation/review-summary-latest.json and .md")
    sp.add_argument("--summary-path", default="", help="custom reports/automation/*.json review summary path")

    sp = automation_sub.add_parser("review-feedback", help="Record accept/reject/defer feedback for a review-summary card")
    add_automation_common(sp)
    sp.add_argument("--kind", required=True, help="review card kind, for example memory_importance or report_review")
    sp.add_argument("--card-id", default="", help="review card id from review-summary output")
    sp.add_argument("--decision", choices=["accept", "reject", "defer"], required=True, help="human or agent review decision")
    sp.add_argument("--reason", required=True, help="short reason for this feedback")
    sp.add_argument("--recommended-action", default="", help="optional action label to group learning feedback")
    sp.add_argument("--score", type=float, default=None, help="optional 0..1 feedback score; defaults depend on decision")
    sp.add_argument("--summary-path", default="", help="review-summary JSON path to enrich the feedback event")
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before a group is considered learnable")
    sp.add_argument("--write-learning-policy", action="store_true", help="rewrite reports/automation/learning_policy.json after recording feedback")

    sp = automation_sub.add_parser("learning-health", help="Show a short health panel for automation learning feedback")
    add_automation_common(sp)
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before learning is considered warm")
    sp.add_argument("--write-health", action="store_true", help="write reports/automation/learning-health-latest.json and .md")
    sp.add_argument("--health-path", default="", help="custom reports/automation/*.json learning health path")

    sp = automation_sub.add_parser("fleet-health", help="Show a multi-Agent automation health panel")
    add_automation_common(sp)
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before learning is considered warm")
    sp.add_argument("--max-status-age-minutes", type=int, default=24 * 60, help="maximum age for shared update-status before it is stale")
    sp.add_argument("--write-health", action="store_true", help="write reports/automation/fleet-health-latest.json and .md")
    sp.add_argument("--health-path", default="", help="custom reports/automation/*.json fleet health path")

    sp = automation_sub.add_parser("inbox", help="Show the shortest review queue for automation candidates and reports")
    add_automation_common(sp)
    sp.add_argument("--include-content", action="store_true", help="include redacted candidate content in JSON output")
    sp.add_argument("--include-transcripts", action="store_true", help="include metadata-only transcript discovery hints")
    sp.add_argument("--transcript-limit", type=int, default=5, help="maximum transcript discovery hints")
    sp.add_argument("--write-handoff", action="store_true", help="write reports/automation/inbox-latest.json")
    sp.add_argument("--handoff-path", default="", help="custom reports/automation/*.json inbox handoff path")

    sp = automation_sub.add_parser("handoff", help="Print the latest compact automation handoff for the next agent")
    add_automation_common(sp)
    sp.add_argument("--source", choices=["auto", "cycle", "inbox"], default="auto",
                    help="which handoff to read; auto prefers cycle-latest.md and attaches fleet-health when present")
    sp.add_argument("--handoff-path", default="", help="custom reports/automation/*.md or *.json handoff path")

    sp = automation_sub.add_parser("eval", help="Evaluate automation feedback and candidate outcomes")
    add_automation_common(sp)
    sp.add_argument("--min-events", type=int, default=5, help="minimum feedback events before a group is considered learnable")
    sp.add_argument(
        "--write-learning-policy",
        action="store_true",
        help="write reports/automation/learning_policy.json with bounded curation priority hints",
    )

    sp = automation_sub.add_parser("doctor", help="Check automation readiness")
    add_automation_common(sp)
