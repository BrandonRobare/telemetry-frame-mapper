"""Headless full-pipeline CLI: dvg-pipeline.

Usage:
  dvg-pipeline <job.yml>           Run a batch pipeline job
  dvg-pipeline --dry-run <job.yml>  Validate and print the plan
  dvg-pipeline --help              Show this help
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from drone_video_geotagger.pipeline import PipelineResult, load_and_run, plan_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dvg-pipeline",
        description="Headless full-pipeline CLI for batch telemetry-frame-mapper jobs.",
    )
    parser.add_argument(
        "job_file",
        type=Path,
        help="Path to a YAML job spec (see docs/examples/pipeline-job-spec.yml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the job spec and print the step plan without executing destructive steps.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Override the output_root from the YAML job spec.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Override the log_dir from the YAML job spec.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


def _format_result(result: PipelineResult) -> str:
    lines = [
        f"Pipeline: {result.name}",
        f"Started:  {result.started_at.isoformat()}",
        f"Finished: {result.finished_at.isoformat()}",
        f"Duration: {(result.finished_at - result.started_at).total_seconds():.1f}s",
        f"Dry-run:  {result.dry_run}",
        f"Success:  {result.success}",
        "",
    ]
    for step in result.steps:
        status = "OK" if step.success else "FAIL"
        lines.append(f"  [{status}] Step {step.step_index + 1}: {step.kind.value}")
        if step.output:
            lines.append(f"         {step.output}")
        if step.error:
            lines.append(f"         ERROR: {step.error}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    job_file: Path = args.job_file
    if not job_file.exists():
        print(f"error: job file not found: {job_file}", file=sys.stderr)
        return 2

    if args.dry_run:
        try:
            plan = plan_job(job_file)
        except Exception as exc:
            print(f"error: plan failed: {exc}", file=sys.stderr)
            return 1
        print(plan)
    else:
        try:
            result = load_and_run(
                yaml_path=job_file,
                dry_run=False,
                output_root=args.output_root,
                log_dir=args.log_dir,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(_format_result(result))
        sys.exit(result.exit_code)

    return 0