import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

import httpx


EVAL_DIR = Path(__file__).resolve().parent


def normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def evaluate_body(
    case: dict,
    body: dict,
    document_id: str,
) -> list[str]:
    issues = []
    kind = case["kind"]

    if kind == "agent":
        if body.get("action") != case["expected_action"]:
            issues.append("incorrect agent action")

        if body.get("tool_used") != case["expected_tool"]:
            issues.append("incorrect tool selection")

        answer = str(body.get("answer", ""))

    elif kind == "rag":
        if body.get("supported") is not case["expected_supported"]:
            issues.append("incorrect support decision")

        answer = str(body.get("answer", ""))

        if not case["expected_supported"] and body.get("citations"):
            issues.append("unsupported answer contains citations")

    elif kind == "draft":
        answer = (
            str(body.get("title", ""))
            + " "
            + str(body.get("description", ""))
        )

        if body.get("requires_confirmation") is not True:
            issues.append("draft does not require confirmation")

    else:
        return ["unknown evaluation type"]

    answer_normalised = normalise(answer)

    for phrase in case.get("required_phrases", []):
        if normalise(phrase) not in answer_normalised:
            issues.append(f"missing expected phrase: {phrase}")

    expected_page = case.get("evidence_page")

    if expected_page is not None:
        if kind == "draft":
            if body.get("evidence_page") != expected_page:
                issues.append("incorrect draft evidence page")

            expected_ref = (
                f"document:{document_id}:page:{expected_page}"
            )

            if body.get("source_ref") != expected_ref:
                issues.append("incorrect draft source reference")

        else:
            citations = body.get("citations", [])

            matching = any(
                citation.get("document_id") == document_id
                and citation.get("page_number") == expected_page
                for citation in citations
            )

            if not matching:
                issues.append("missing expected source citation")

    return issues


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, ceil(fraction * len(ordered)) - 1)

    return round(ordered[index], 2)


def request_payload(case: dict, document_id: str) -> tuple[str, dict]:
    kind = case["kind"]

    if kind == "agent":
        return "/agent/run", {"message": case["query"]}

    if kind == "rag":
        return "/knowledge/ask", {"question": case["query"]}

    return (
        "/agent/workflows/draft",
        {
            "document_id": document_id,
            "instruction": case["query"],
        },
    )


def run_case(
    client: httpx.Client,
    case: dict,
    document_id: str,
    token: str,
) -> dict:
    path, payload = request_payload(case, document_id)

    start = time.perf_counter()

    try:
        response = client.post(
            path,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        latency_ms = round(
            (time.perf_counter() - start) * 1000,
            2,
        )

        expected_status = case.get("expected_status", 200)
        issues = []

        if response.status_code != expected_status:
            issues.append(
                f"HTTP {response.status_code}, expected {expected_status}"
            )

        if response.status_code == 200 and expected_status == 200:
            try:
                body = response.json()

                issues.extend(
                    evaluate_body(case, body, document_id)
                )
            except (ValueError, TypeError, KeyError) as exc:
                issues.append(f"invalid response: {exc}")

        return {
            "id": case["id"],
            "kind": case["kind"],
            "passed": not issues,
            "latency_ms": latency_ms,
            "issues": issues,
        }

    except httpx.RequestError as exc:
        return {
            "id": case["id"],
            "kind": case["kind"],
            "passed": False,
            "latency_ms": round(
                (time.perf_counter() - start) * 1000,
                2,
            ),
            "issues": [f"request error: {type(exc).__name__}"],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )

    args = parser.parse_args()

    if not 1 <= args.runs <= 10:
        parser.error("--runs must be between 1 and 10")

    admin_token = os.getenv("OPSPILOT_EVAL_TOKEN")
    finance_token = os.getenv("OPSPILOT_EVAL_FINANCE_TOKEN")

    if not admin_token:
        raise SystemExit(
            "Set OPSPILOT_EVAL_TOKEN before running evaluations."
        )

    dataset = json.loads(
        (EVAL_DIR / "cases.json").read_text(encoding="utf-8")
    )

    document_id = dataset["document_id"]
    results = []
    skipped = []

    with httpx.Client(
        base_url=args.base_url,
        timeout=180.0,
    ) as client:
        for run_number in range(1, args.runs + 1):
            for case in dataset["cases"]:
                token = admin_token

                if case["kind"] == "finance_draft":
                    if not finance_token:
                        skipped.append(case["id"])
                        continue

                    token = finance_token

                result = run_case(
                    client,
                    case,
                    document_id,
                    token,
                )

                result["run"] = run_number
                results.append(result)

                label = "PASS" if result["passed"] else "FAIL"

                print(
                    f"[{label}] {case['id']}: "
                    f"{result['latency_ms']} ms"
                )

                for issue in result["issues"]:
                    print(f"    {issue}")

    passed = sum(result["passed"] for result in results)
    total = len(results)

    latencies = [
        result["latency_ms"]
        for result in results
    ]

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs": args.runs,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate_pct": round(
            100 * passed / total if total else 0,
            2,
        ),
        "median_latency_ms": round(
            statistics.median(latencies) if latencies else 0,
            2,
        ),
        "p95_latency_ms": percentile(latencies, 0.95),
        "skipped": sorted(set(skipped)),
        "results": results,
    }

    output_dir = EVAL_DIR / "results"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "latest.json"

    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Passed: {passed}/{total}")
    print(f"Pass rate: {report['pass_rate_pct']}%")
    print(f"Median latency: {report['median_latency_ms']} ms")
    print(f"P95 latency: {report['p95_latency_ms']} ms")
    print(f"Report: {output_path}")

    if skipped:
        print(f"Skipped optional security tests: {sorted(set(skipped))}")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()