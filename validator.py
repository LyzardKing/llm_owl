import argparse
import json
import logging
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import owlready2
import yaml
from rdflib import Graph

# Module-level logger (can be configured in `main`)
LOG: logging.Logger = logging.getLogger("owl_llm.validator")
LOG.addHandler(logging.NullHandler())


def _row_to_string(row) -> str:
    # Convert a SPARQL result row to a simple string representation
    if hasattr(row, "asdict"):
        d = row.asdict()
        # join values by pipe for deterministic comparison
        return "|".join(str(v) for v in d.values())
    # fallback for tuple-like rows
    try:
        return "|".join(str(x) for x in row)
    except Exception:
        return str(row)


def validate_ttl(ttl_path: str) -> bool:
    """Validate a Turtle/TTL file for syntax correctness."""
    g = Graph()
    with open(ttl_path, "r", encoding="utf-8") as f:
        ttl_text = f.read()
    try:
        g.parse(data=ttl_text, format="turtle")
        emit_log("ttl_valid", path=ttl_path)
        return True
    except Exception as e:
        print("Turtle validation error:", str(e))
        emit_log("ttl_invalid", path=ttl_path, error=str(e))
        return False


def check_consistency(ontology: Graph) -> list[str]:
    """Check if an OWL ontology is internally consistent."""
    world = owlready2.World()
    graph = world.as_rdflib_graph()
    with world.get_ontology("http://localhost/"):
        graph += ontology
    try:
        owlready2.sync_reasoner_pellet(world, debug=0)
    except owlready2.OwlReadyInconsistentOntologyError:
        emit_log("consistency_error", error="OwlReadyInconsistentOntologyError")
        return ["The ontology is inconsistent"]
    inconsistent_classes = ", ".join(c.__name__ for c in world.inconsistent_classes())
    if inconsistent_classes:
        emit_log("consistency_issues", inconsistent_classes=inconsistent_classes)
        return [
            f"There are inconsistent classes in the ontology: {inconsistent_classes}"
        ]
    emit_log("consistency_ok")
    return []


def setup_structured_logger(path: str) -> logging.Logger:
    """Create a logger that writes JSON lines to `path`.

    Each log entry will be a single JSON object per line.
    """
    logger = logging.getLogger("owl_llm.validator")
    logger.setLevel(logging.INFO)
    # remove existing handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    # Keep message raw (we log JSON ourselves)
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    return logger


def emit_log(stage: str, **fields: Any) -> None:
    """Emit a structured JSON-line log entry using the module `LOG`.

    `stage` is a short string describing the event. Additional keyword
    arguments are added to the JSON object. The function is resilient to
    formatting/logging errors and falls back to printing if necessary.
    """
    payload = {"timestamp": datetime.now(UTC).isoformat() + "Z", "stage": stage}
    payload.update(fields)
    # try:
    LOG.info(json.dumps(payload, ensure_ascii=False))#, indent=4))
    # except Exception:
    #     try:
    #         # Last resort: print the JSON payload
    #         print(json.dumps(payload, ensure_ascii=False, indent=4))
    #     except Exception:
    #         # give up silently
    #         pass


def validate_with_competency_questions_file(
    ttl_file: str, cq_file: str
) -> tuple[bool, Dict[str, Any]]:
    ttl_text = open(ttl_file, "r", encoding="utf-8").read()
    cqs = _load_json(cq_file)

    return validate_with_competency_questions(ttl_text, cqs)


def validate_with_competency_questions(
    ttl_text: str, competency_questions: List[Dict[str, Any]]
) -> tuple[bool, Dict[str, Any]]:
    """Validate an OWL/Turtle string against competency questions.

    Each competency question is a dict with keys:
      - id: optional identifier
      - sparql: the SPARQL ASK/SELECT query to run against the graph
      - expected: optional expected result. If an integer, it's compared
          to the number of result rows. If a list, the list of stringified
          rows must match the query results (order-insensitive). If omitted,
          the question passes when the query returns at least one row (or
          True for ASK).

    Returns a report dict with per-question results and a summary.
    """
    g = Graph()
    g.parse(data=ttl_text, format="turtle")

    results: List[Dict[str, Any]] = []
    passed_count = 0

    # Log start of validation run
    emit_log("CQ_validation_start", total_questions=len(competency_questions))

    for cq in competency_questions:
        output = validate_with_competency_question(g, cq, results)
        if output and output.get("passed", True):
            passed_count += 1
        results.append(output)

        # Log each question's result as a structured JSON line
        emit_log(
            "competency_question",
            id=output.get("id"),
            passed=output.get("passed"),
            error=output.get("error"),
            expected=output.get("expected"),
            actual=output.get("actual"),
            sparql=output.get("sparql"),
            question=output.get("question"),
        )

    summary = {"total": len(competency_questions), "passed": passed_count}
    output = {"summary": summary, "results": results}

    # Log end of validation run
    emit_log("CQ_validation_end", summary=summary)

    return passed_count == len(competency_questions), output


def validate_with_competency_question(
    g: Graph, cq: Dict[str, Any], results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    qid = cq.get("id") or cq.get("name") or "unnamed"
    sparql = cq.get("sparql", "")
    expected = cq.get("expected", None)
    question = cq.get("question", "")
    entry: Dict[str, Any] = {
        "id": qid,
        "sparql": sparql,
        "expected": expected,
        "question": question,
    }

    try:
        res = g.query(sparql)
    except Exception as e:
        entry.update({"passed": False, "error": str(e), "actual": None})
        # Log this error immediately
        emit_log("competency_question_error", id=qid, error=str(e), sparql=sparql)
        return entry

    # ASK query returns boolean
    if isinstance(res, bool):
        actual_bool = res
        passed = True if expected is None and actual_bool else (expected == actual_bool)
        entry.update({"passed": passed, "actual": actual_bool})
        return entry

    # For SELECT queries, collect rows as strings
    rows = [_row_to_string(r) for r in res]
    entry["actual"] = rows

    if isinstance(expected, int):
        passed = len(rows) == expected
    elif isinstance(expected, list):
        passed = set(rows) == set(str(x) for x in expected)
    else:
        # default: pass if any rows returned
        passed = len(rows) > 0

    entry["passed"] = passed
    return entry


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        # return json.load(f)
        return yaml.safe_load(f)
    

def pretty_print_errors(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    summary = report.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    lines.append(f"Competency Questions Validation Report:")
    lines.append(f"  Passed {passed} out of {total} questions.")
    for result in report.get("results", []):
        if not result.get("passed", False):
            qid = result.get("id", "unnamed")
            error = result.get("error", "")
            expected = result.get("expected", "")
            actual = result.get("actual", "")
            question = result.get("question", "")
            lines.append(f"- Question ID: {qid}")
            lines.append(f"  Question: {question}")
            if error:
                lines.append(f"  Error: {error}")
            else:
                lines.append(f"  Expected: {expected}")
                lines.append(f"  Actual: {actual}")
    return "\n".join(lines)


def log_report(report: Dict[str, Any], out: Optional[str] = None) -> str:
    # Build the log as a list of lines, print them, and return as a single string.
    lines: List[str] = []
    report_path = os.path.join(out, "validation_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        LOG.info(f"Wrote report to {report_path}")
    except Exception as e:
        LOG.error(f"Failed to write report to {report_path}: {e}")

    return pretty_print_errors(report)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ttl-file", required=True, help="Path to Turtle/TTL file to validate"
    )
    p.add_argument(
        "--cqs-file", required=True, help="Path to competency questions JSON file"
    )
    p.add_argument("--out", help="Path to write JSON report (defaults to stdout)")
    p.add_argument(
        "--log-file",
        help="Path to write structured validation steps log (JSON-lines). Defaults to validation_steps.json.",
        default="validation_steps.jsonl",
    )
    args = p.parse_args()

    # Configure structured logger
    try:
        global LOG
        LOG = setup_structured_logger(args.log_file)
    except Exception:
        # fallback to existing logger
        pass
    validate_ttl(args.ttl_file)
    check_consistency(Graph().parse(args.ttl_file, format="turtle"))
    _, report = validate_with_competency_questions_file(args.ttl_file, args.cqs_file)
    # log_report(report, args.out)


if __name__ == "__main__":
    main()
