"""Run analytics metrics over indexed curated pipeline outputs."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from analytics.config import (
    load_homepage_analytics_config,
    load_keyword_config,
    load_topic_rules,
    load_topic_weights,
)
from analytics.homepage import generate_homepage_data, write_homepage_data
from analytics.employment import generate_employment_data, write_employment_data
from analytics.fertility import generate_fertility_data, write_fertility_data
from analytics.input_resolver import HomepageInputResolver
from analytics.io import load_curated_dataset
from analytics.policy_support import (
    generate_policy_support_data,
    write_policy_support_data,
)
from analytics.published_snapshot import publish_homepage_snapshot
from analytics.youth_keyword_frequency import (
    calculate_youth_keyword_frequency,
    write_youth_keyword_frequency,
)
from analytics.youth_topic_weight import calculate_youth_topic_weights, write_youth_topic_weights
from analytics.youth_participation import (
    generate_youth_participation_data,
    write_youth_participation_data,
)


def _load_indexed_dataset(dataset: str, *, output_dir: Path) -> list[dict]:
    """Read an authoritative curated dataset, naming the fix when it is absent.

    These metrics deliberately read only the dataset index rather than falling
    back to curated paths, so a missing entry must say which command rebuilds
    it instead of surfacing a bare lookup error.
    """

    try:
        return load_curated_dataset(dataset, output_dir=output_dir)
    except ValueError as exc:
        raise SystemExit(
            f"analytics input unavailable: {exc}\n"
            f"Rebuild the index entry for {dataset!r}, then re-run this metric:\n"
            f"  PYTHONPATH=src python src/run_pipeline.py --refresh-profile monthly "
            f"--datasets {dataset} --force --retention-years 8 "
            f"--output-dir {output_dir}"
        ) from exc


def _public_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    """Remove private quality metadata before embedding an analysis."""

    return {key: value for key, value in result.items() if key != "_quality"}


def _default_full_snapshot_id(generated_at: str) -> str:
    """Build a collision-resistant development id from the shared run time."""

    parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return f"dev-full-{parsed.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _run_all_analytics(
    args: argparse.Namespace, *, output_dir: Path, config_dir: Path
) -> int:
    """Generate every public analysis and publish one complete snapshot."""

    if args.annual_start_roc > args.annual_end_roc:
        raise SystemExit("--annual-start-roc must be less than or equal to --annual-end-roc")

    config = load_homepage_analytics_config(config_dir / "homepage_analytics.json")
    annual_years = tuple(range(args.annual_start_roc, args.annual_end_roc + 1))
    if args.population_reference_roc not in annual_years:
        raise SystemExit("--population-reference-roc must be within the annual ROC range")
    config = replace(
        config,
        annual_years_roc=annual_years,
        population_reference_year_roc=args.population_reference_roc,
    )
    resolver = HomepageInputResolver.from_paths(output_dir, config_dir)

    homepage_result = generate_homepage_data(resolver=resolver, config=config)
    output_path, quality_path = write_homepage_data(homepage_result, output_dir=output_dir)
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")

    analyses: dict[str, Mapping[str, Any]] = {}
    analysis_quality: dict[str, Mapping[str, Any]] = {}

    def add_analysis(name: str, result: Mapping[str, Any]) -> None:
        analyses[name] = _public_payload(result)
        quality = result.get("_quality")
        analysis_quality[name] = dict(quality) if isinstance(quality, Mapping) else {}

    employment_result = generate_employment_data(
        resolver=resolver,
        config=config,
        homepage_result=homepage_result,
    )
    output_path, quality_path = write_employment_data(
        employment_result, output_dir=output_dir
    )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    add_analysis("employment", employment_result)

    fertility_result = generate_fertility_data(
        resolver=resolver,
        config=config,
        homepage_result=homepage_result,
    )
    output_path, quality_path = write_fertility_data(
        fertility_result, output_dir=output_dir
    )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    add_analysis("fertility", fertility_result)

    participation_result = generate_youth_participation_data(
        resolver=resolver,
        config=config,
        config_dir=config_dir,
    )
    output_path, quality_path = write_youth_participation_data(
        participation_result, output_dir=output_dir
    )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    add_analysis("participation", participation_result)

    policy_support_result = generate_policy_support_data(resolver=resolver)
    output_path, quality_path = write_policy_support_data(
        policy_support_result, output_dir=output_dir
    )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    add_analysis("policy_support", policy_support_result)

    weights = load_topic_weights(config_dir / "youth_topic_weights.json")
    join_rows = _load_indexed_dataset("join_proposals", output_dir=output_dir)
    minute_rows = _load_indexed_dataset("youth_council_minutes", output_dir=output_dir)

    rules = load_topic_rules(config_dir / "youth_topic_rules.json")
    topic_result = calculate_youth_topic_weights(
        join_rows, minute_rows, rules=rules, weights=weights
    )
    output_path, quality_path = write_youth_topic_weights(
        topic_result, output_dir=output_dir
    )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    add_analysis("topic_weight", topic_result)

    keyword_config = load_keyword_config(config_dir / "youth_keyword_config.json")
    keyword_result = calculate_youth_keyword_frequency(
        join_rows, minute_rows, config=keyword_config, weights=weights
    )
    output_path, quality_path = write_youth_keyword_frequency(
        keyword_result, output_dir=output_dir
    )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    add_analysis("keyword_frequency", keyword_result)

    if not args.publish:
        return 0

    snapshot_id = args.snapshot_id or _default_full_snapshot_id(
        str(homepage_result["generated_at"])
    )
    published = publish_homepage_snapshot(
        homepage_result,
        homepage_result.get("_quality"),
        output_dir=output_dir,
        snapshot_id=snapshot_id,
        analyses=analyses,
        analysis_quality=analysis_quality,
        update_current=True,
    )
    print(f"complete published snapshot written: {published.snapshot_dir}")
    print(f"published pointer written: {published.current_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run data-pipeline analytics")
    parser.add_argument(
        "--metric",
        required=True,
        choices=(
            "all",
            "youth_topic_weight",
            "youth_keyword_frequency",
            "homepage",
            "employment",
            "youth_participation",
            "fertility",
            "policy_support",
        ),
    )
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--annual-start-roc", type=int, default=110)
    parser.add_argument("--annual-end-roc", type=int, default=114)
    parser.add_argument("--population-reference-roc", type=int, default=114)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish analytics as a versioned local snapshot",
    )
    parser.add_argument(
        "--snapshot-id",
        help="Optional safe id for the published homepage snapshot",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    config_dir = Path(args.config_dir)
    if args.metric == "all":
        return _run_all_analytics(args, output_dir=output_dir, config_dir=config_dir)
    if args.publish and args.metric not in {
        "homepage",
        "employment",
        "youth_participation",
        "fertility",
        "policy_support",
    }:
        parser.error(
            "--publish is only supported with --metric homepage, employment, youth_participation, fertility, or policy_support"
        )
    if args.metric == "policy_support":
        resolver = HomepageInputResolver.from_paths(output_dir, config_dir)
        policy_support_result = generate_policy_support_data(resolver=resolver)
        output_path, quality_path = write_policy_support_data(
            policy_support_result, output_dir=output_dir
        )
        print(f"analytics written: {output_path}")
        print(f"quality written: {quality_path}")
        if args.publish:
            config = load_homepage_analytics_config(config_dir / "homepage_analytics.json")
            homepage_result = generate_homepage_data(resolver=resolver, config=config)
            public_policy_support = {
                key: value
                for key, value in policy_support_result.items()
                if key != "_quality"
            }
            published = publish_homepage_snapshot(
                homepage_result,
                homepage_result.get("_quality"),
                output_dir=output_dir,
                snapshot_id=args.snapshot_id,
                analyses={"policy_support": public_policy_support},
                analysis_quality={
                    "policy_support": policy_support_result.get("_quality", {})
                },
                update_current=False,
            )
            print(f"published candidate snapshot written: {published.snapshot_dir}")
        return 0
    if args.metric in {"homepage", "employment", "youth_participation", "fertility"}:
        if args.annual_start_roc > args.annual_end_roc:
            parser.error("--annual-start-roc must be less than or equal to --annual-end-roc")
        config = load_homepage_analytics_config(config_dir / "homepage_analytics.json")
        annual_years = tuple(range(args.annual_start_roc, args.annual_end_roc + 1))
        if args.population_reference_roc not in annual_years:
            parser.error("--population-reference-roc must be within the annual ROC range")
        config = replace(
            config,
            annual_years_roc=annual_years,
            population_reference_year_roc=args.population_reference_roc,
        )
        resolver = HomepageInputResolver.from_paths(output_dir, config_dir)
        homepage_result = generate_homepage_data(resolver=resolver, config=config)
        if args.metric == "homepage":
            output_path, quality_path = write_homepage_data(homepage_result, output_dir=output_dir)
            print(f"analytics written: {output_path}")
            print(f"quality written: {quality_path}")
            if args.publish:
                published = publish_homepage_snapshot(
                    homepage_result,
                    homepage_result.get("_quality"),
                    output_dir=output_dir,
                    snapshot_id=args.snapshot_id,
                    update_current=False,
                )
                print(f"published candidate snapshot written: {published.snapshot_dir}")
            return 0

        if args.metric == "youth_participation":
            participation_result = generate_youth_participation_data(
                resolver=resolver,
                config=config,
                config_dir=config_dir,
            )
            output_path, quality_path = write_youth_participation_data(
                participation_result, output_dir=output_dir
            )
            print(f"analytics written: {output_path}")
            print(f"quality written: {quality_path}")
            if args.publish:
                public_participation = {
                    key: value
                    for key, value in participation_result.items()
                    if key != "_quality"
                }
                published = publish_homepage_snapshot(
                    homepage_result,
                    homepage_result.get("_quality"),
                    output_dir=output_dir,
                    snapshot_id=args.snapshot_id,
                    analyses={"participation": public_participation},
                    analysis_quality={
                        "participation": participation_result.get("_quality", {})
                    },
                    update_current=False,
                )
                print(f"published candidate snapshot written: {published.snapshot_dir}")
            return 0

        if args.metric == "fertility":
            fertility_result = generate_fertility_data(
                resolver=resolver,
                config=config,
                homepage_result=homepage_result,
            )
            output_path, quality_path = write_fertility_data(
                fertility_result, output_dir=output_dir
            )
            print(f"analytics written: {output_path}")
            print(f"quality written: {quality_path}")
            if args.publish:
                public_fertility = {
                    key: value
                    for key, value in fertility_result.items()
                    if key != "_quality"
                }
                published = publish_homepage_snapshot(
                    homepage_result,
                    homepage_result.get("_quality"),
                    output_dir=output_dir,
                    snapshot_id=args.snapshot_id,
                    analyses={"fertility": public_fertility},
                    analysis_quality={"fertility": fertility_result.get("_quality", {})},
                    update_current=False,
                )
                print(f"published candidate snapshot written: {published.snapshot_dir}")
            return 0

        employment_result = generate_employment_data(
            resolver=resolver,
            config=config,
            homepage_result=homepage_result,
        )
        output_path, quality_path = write_employment_data(
            employment_result, output_dir=output_dir
        )
        print(f"analytics written: {output_path}")
        print(f"quality written: {quality_path}")
        if args.publish:
            public_employment = {
                key: value for key, value in employment_result.items() if key != "_quality"
            }
            published = publish_homepage_snapshot(
                homepage_result,
                homepage_result.get("_quality"),
                output_dir=output_dir,
                snapshot_id=args.snapshot_id,
                analyses={"employment": public_employment},
                analysis_quality={"employment": employment_result.get("_quality", {})},
                update_current=False,
            )
            print(f"published candidate snapshot written: {published.snapshot_dir}")
        return 0

    weights = load_topic_weights(config_dir / "youth_topic_weights.json")
    join_rows = _load_indexed_dataset("join_proposals", output_dir=output_dir)
    minute_rows = _load_indexed_dataset("youth_council_minutes", output_dir=output_dir)
    if args.metric == "youth_topic_weight":
        rules = load_topic_rules(config_dir / "youth_topic_rules.json")
        result = calculate_youth_topic_weights(
            join_rows, minute_rows, rules=rules, weights=weights
        )
        output_path, quality_path = write_youth_topic_weights(result, output_dir=output_dir)
    else:
        keyword_config = load_keyword_config(config_dir / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            join_rows, minute_rows, config=keyword_config, weights=weights
        )
        output_path, quality_path = write_youth_keyword_frequency(
            result, output_dir=output_dir
        )
    print(f"analytics written: {output_path}")
    print(f"quality written: {quality_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
