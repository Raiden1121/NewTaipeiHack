"""Run analytics metrics over indexed curated pipeline outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from analytics.config import load_keyword_config, load_topic_rules, load_topic_weights
from analytics.io import load_curated_dataset
from analytics.youth_keyword_frequency import (
    calculate_youth_keyword_frequency,
    write_youth_keyword_frequency,
)
from analytics.youth_topic_weight import calculate_youth_topic_weights, write_youth_topic_weights


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run data-pipeline analytics")
    parser.add_argument(
        "--metric",
        required=True,
        choices=("youth_topic_weight", "youth_keyword_frequency"),
    )
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--config-dir", default="config")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    config_dir = Path(args.config_dir)
    weights = load_topic_weights(config_dir / "youth_topic_weights.json")
    join_rows = load_curated_dataset("join_proposals", output_dir=output_dir)
    minute_rows = load_curated_dataset("youth_council_minutes", output_dir=output_dir)
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
