from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from app import AGENT, DEFAULT_SOURCES_DIR


def evaluate_golden(path: Path | None = None, repetitions: int = 1) -> dict[str, Any]:
    golden_path = path or (DEFAULT_SOURCES_DIR / "golden_cases.csv")
    with golden_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records = []
    for row in rows:
        expected_tools = set(filter(None, row.get("expected_tools", "").split(";")))
        for repetition in range(1, repetitions + 1):
            result = AGENT.analyze(row["input"], source="golden_dataset")
            behavior = result["behavior_ia"]
            output = behavior["raw_output"]
            actual_tools = set(result["trace"]["selected_tools"])
            expected_error = row.get("expected_error", "")
            error_ok = (
                output.get("error_detectado") == expected_error
                or expected_error in {"Unknown", "Request for remediation"}
                and output.get("error_detectado") == "No determinado"
            )
            record = {
                "case_id": row["case_id"],
                "repetition": repetition,
                "behavior_verdict": behavior["verdict"],
                "system_verdict": result["system_protected"]["verdict"],
                "tools_expected": sorted(expected_tools),
                "tools_actual": sorted(actual_tools),
                "routing_ok": actual_tools == expected_tools,
                "error_ok": error_ok,
                "out_of_scope_ok": output.get("fuera_de_alcance") == (row.get("out_of_scope") == "True"),
                "trace_id": result["trace_id"],
            }
            record["case_pass"] = bool(record["routing_ok"] and record["error_ok"] and record["out_of_scope_ok"] and behavior["verdict"] == "PASS")
            records.append(record)

    total = len(records)
    return {
        "dataset": str(golden_path),
        "cases": len(rows),
        "repetitions": repetitions,
        "records": records,
        "summary": {
            "behavior_pass": sum(record["behavior_verdict"] == "PASS" for record in records),
            "system_pass": sum(record["system_verdict"] == "PASS" for record in records),
            "routing_pass": sum(record["routing_ok"] for record in records),
            "case_pass": sum(record["case_pass"] for record in records),
            "total_runs": total,
            "dataset_warning": "El dataset actual tiene menos de 30 casos; no es evidencia estadística suficiente." if len(rows) < 30 else None,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evalúa el golden dataset del DevOps Triage MVP")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 20:
        raise SystemExit("--repetitions debe estar entre 1 y 20")
    print(json.dumps(evaluate_golden(args.dataset, args.repetitions), ensure_ascii=False, indent=2))
