
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

load_dotenv(dotenv_path=backend_dir / ".env")

from rag_eval import LLMJudge, load_golden_cases, run_eval_suite
from rag_eval.runner import write_reports


DEFAULT_UID = "vpq1p0UzcCSLAh1d18WgZZWPBE63"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TomeHub golden-set RAG evaluation.")
    parser.add_argument("--uid", default=DEFAULT_UID, help="Firebase UID to evaluate against.")
    parser.add_argument(
        "--dataset",
        default=str(backend_dir / "data" / "golden_dataset.json"),
        help="Path to the golden dataset JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(backend_dir / "reports"),
        help="Directory where markdown/json reports are written.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Limit the number of cases. 0 means all.",
    )
    parser.add_argument(
        "--pass-score",
        type=int,
        default=4,
        help="Minimum judge score required for a case to pass.",
    )
    parser.add_argument(
        "--fail-under-pass-rate",
        type=float,
        default=0.0,
        help="Exit with code 1 if pass rate falls below this ratio (0-1).",
    )
    parser.add_argument(
        "--fail-under-average-score",
        type=float,
        default=0.0,
        help="Exit with code 1 if average score falls below this threshold (0-5).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_golden_cases(args.dataset)
    if args.max_cases > 0:
        cases = cases[: args.max_cases]
    if not cases:
        print(f"No eval cases found in {args.dataset}")
        return 1

    print(f"Running TomeHub RAG eval on {len(cases)} cases")
    print(f"Dataset: {args.dataset}")
    print(f"UID: {args.uid}")

    results, summary = run_eval_suite(
        cases,
        args.uid,
        LLMJudge(),
        pass_score=args.pass_score,
    )
    dataset_name = Path(args.dataset).stem
    markdown_path, json_path = write_reports(args.output_dir, dataset_name, results, summary)

    print("")
    print(f"Pass rate: {summary.pass_rate:.1%}")
    print(f"Average score: {summary.average_score:.2f}/5")
    print(f"Average latency: {summary.average_latency_sec:.2f}s")
    print(f"Classifications: {summary.classifications}")
    print(f"Markdown report: {markdown_path}")
    print(f"JSON report: {json_path}")

    failed_threshold = False
    if args.fail_under_pass_rate and summary.pass_rate < args.fail_under_pass_rate:
        print(
            f"FAIL: pass rate {summary.pass_rate:.1%} is below threshold {args.fail_under_pass_rate:.1%}"
        )
        failed_threshold = True
    if args.fail_under_average_score and summary.average_score < args.fail_under_average_score:
        print(
            "FAIL: average score "
            f"{summary.average_score:.2f} is below threshold {args.fail_under_average_score:.2f}"
        )
        failed_threshold = True
    return 1 if failed_threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())
