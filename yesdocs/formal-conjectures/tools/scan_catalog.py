#!/usr/bin/env python3
"""Static scan of a google-deepmind/formal-conjectures checkout.

The scan is deliberately static: it reads the .lean sources as text, extracts
every declaration that carries a ``@[category ...]`` attribute together with
its AMS classification, answer polarity, formal-proof link, statement-size
features and the URLs referenced by the file. It does not elaborate Lean and
does not need a built project.

Determinism is part of the contract: the JSON output carries no timestamps
and no local paths, files and references are sorted, so re-running the scan on
the same commit reproduces byte-identical data. The commit hash is resolved
from the checkout when available.

Usage:
    python3 scan_catalog.py CATALOG_DIR [--json OUT]

Exit codes: 0 on success, 2 when CATALOG_DIR has no FormalConjectures/ tree.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "formal-conjectures-scan/1"
STATEMENT_ROOT = "FormalConjectures"
SOURCE_URL = "https://github.com/google-deepmind/formal-conjectures"

# A category attribute must start its line (a docstring may close right
# before it: ``-/@[category ...]`` counts); an inline mention inside prose
# (``these `@[category test, ...]` results``) is not a declaration.
_ATTRIBUTE_RE = re.compile(
    r"^[ \t]*(?:-/)?[ \t]*@\[(?P<body>category[^\]]*)\]", re.MULTILINE
)
_KIND_RE = re.compile(
    r"[ \t]*(?:(?:noncomputable|private|protected|partial|unsafe)\s+)*"
    r"(?P<kind>theorem|lemma|def|abbrev|instance|example)\b"
)
_NAME_RE = re.compile(r"[ \t\n]+(?P<name>[A-Za-z_][A-Za-z0-9_.'«»]*)")
_ANSWER_RE = re.compile(r"answer\(\s*(?P<value>True|False|sorry)\s*\)")
_FORMAL_PROOF_RE = re.compile(r'formal_proof[^"]*"([^"]+)"')
_MODULE_DOC_RE = re.compile(r"/-!(.*?)-/", re.DOTALL)
_TITLE_RE = re.compile(r"^#\s+(?P<title>\S.*?)\s*$", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s<>\[\]()\"'`]+")
_CROSS_REF_RE = re.compile(r"\b(?:Erdos|Green)(\d+)\b")

# Statement-text feature flags. A fixed, documented list — the scan is a
# coarse filter for the shortlist, not a semantic analysis.
_FEATURES = (
    ("exists", re.compile("\u2203")),
    ("forall", re.compile("\u2200")),
    ("asymptotic", re.compile(r"Tendsto|IsBigO|IsLittleO|IsTheta|Asymptotics|atTop|\u2200\u1da0")),
    ("finset", re.compile(r"\bFinset\b")),
    ("set", re.compile(r"\bSet\b")),
    ("prime", re.compile(r"\bPrime\b")),
    ("machine", re.compile(r"\bTuring\b|\bMachine\b|\bHalting\b")),
    ("sum", re.compile("\u2211")),
    ("sup", re.compile(r"\bsSup\b|\bsInf\b")),
    ("real", re.compile("\u211d")),
    ("nat", re.compile("\u2115")),
    ("int", re.compile("\u2124")),
)

_CATEGORY_CLASSES = ("research open", "research solved", "test", "textbook", "API")


def parse_attributes(body: str) -> dict:
    """The three parts of a category attribute body.

    ``research open, AMS 5 11, formal_proof using lean4 at "URL"`` becomes
    ``{"categories": ["research open"], "ams": ["5", "11"], "formal_proof": URL}``.
    """
    formal_proof = None
    proof_match = _FORMAL_PROOF_RE.search(body)
    if proof_match:
        formal_proof = proof_match.group(1)
        body = body[: proof_match.start()] + body[proof_match.end() :]
    categories = []
    ams = []
    for field in body.split(","):
        field = field.strip()
        if field.startswith("category "):
            categories.append(field[len("category ") :].strip())
        elif field.startswith("AMS "):
            ams.extend(field[len("AMS ") :].split())
    return {"categories": categories, "ams": ams, "formal_proof": formal_proof}


def _statement_text(text: str, start: int) -> str:
    """The text of one declaration's statement: after the name, before the
    top-level ``:=``.

    The theorem type may itself contain ``let ... := ...`` bindings (the
    ``let f := answer(sorry)`` idiom of the corpus): an ``:=`` on a line whose
    part before it names a ``let`` belongs to the type, not to the proof.
    """
    pos = start
    while True:
        index = text.find(":=", pos)
        if index < 0:
            index = len(text)
            break
        line_start = text.rfind("\n", 0, index) + 1
        if re.search(r"\blet\b|\bletI\b", text[line_start:index]):
            pos = index + 2
            continue
        break
    return text[start:index].strip()


def _declarations(text: str):
    """Every ``@[category ...]``-annotated declaration in one file's text.

    Returns ``(declarations, unmatched)``: attributes that do not lead to a
    declaration are counted as unmatched instead of guessed into one.
    """
    declarations = []
    unmatched = 0
    for match in _ATTRIBUTE_RE.finditer(text):
        attrs = parse_attributes(match.group("body"))
        # Between the attribute and the declaration only blank lines and
        # full-line comments may stand (or nothing at all).
        tail = text[match.end() :]
        tail = re.sub(r"^(?:[ \t]*(?:--[^\n]*)?\n)+", "", tail)
        kind_match = _KIND_RE.match(tail)
        if not kind_match:
            unmatched += 1
            continue
        head = tail[kind_match.end() :]
        name_match = _NAME_RE.match(head)
        name = name_match.group("name") if name_match else None
        body_start = kind_match.end() + (name_match.end() if name_match else 0)
        statement = _statement_text(tail, body_start)
        declarations.append(
            {
                "name": name,
                "kind": kind_match.group("kind"),
                "categories": attrs["categories"],
                "ams": attrs["ams"],
                "answer": _answer_value(statement),
                "formal_proof": attrs["formal_proof"],
                "features": [key for key, pattern in _FEATURES if pattern.search(statement)],
                "statement_chars": len(statement),
            }
        )
    return declarations, unmatched


def _answer_value(statement: str):
    match = _ANSWER_RE.search(statement)
    return match.group("value") if match else None


def _title(text: str):
    doc = _MODULE_DOC_RE.search(text)
    if not doc:
        return None
    title = _TITLE_RE.search(doc.group(1))
    return title.group("title") if title else None


def _references(text: str):
    urls = [match.group(0).rstrip(".,;:") for match in _URL_RE.finditer(text)]
    return sorted(set(urls))


def _cross_refs(text: str, collection: str, problem_id):
    own = None
    if problem_id and collection == "ErdosProblems":
        own = f"Erdos{problem_id}"
    elif problem_id and collection == "GreensOpenProblems":
        own = f"Green{problem_id}"
    refs = {match.group(0) for match in _CROSS_REF_RE.finditer(text)}
    refs.discard(own)
    return sorted(refs)


def _problem_id(path: Path, collection: str):
    if path.stem.isdigit() and collection in ("ErdosProblems", "GreensOpenProblems", "OEIS"):
        return path.stem
    return None


def scan_catalog(root) -> dict:
    """The full scan dictionary for one formal-conjectures checkout."""
    root = Path(root)
    base = root / STATEMENT_ROOT
    if not base.is_dir():
        raise SystemExit(f"not a formal-conjectures checkout: {base} is missing")

    files = []
    totals = collections.Counter()
    per_collection = collections.defaultdict(collections.Counter)
    for path in sorted(base.rglob("*.lean")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        collection = path.relative_to(base).parts[0] if len(path.relative_to(base).parts) > 1 else "(root)"
        problem_id = _problem_id(path, collection)
        declarations, unmatched = _declarations(text)
        entry = {
            "path": relative,
            "collection": collection,
            "problem_id": problem_id,
            "title": _title(text),
            "references": _references(text),
            "cross_refs": _cross_refs(text, collection, problem_id),
            "declarations": declarations,
        }
        files.append(entry)
        totals["files"] += 1
        totals["declarations"] += len(declarations)
        totals["unmatched_attributes"] += unmatched
        per_collection[collection]["files"] += 1
        per_collection[collection]["declarations"] += len(declarations)
        for decl in declarations:
            for category in _CATEGORY_CLASSES:
                if category in decl["categories"]:
                    key = category.replace(" ", "_").lower()
                    totals[key] += 1
                    per_collection[collection][key] += 1
                    break
            else:
                totals["other"] += 1
                per_collection[collection]["other"] += 1
            if decl["answer"] == "sorry":
                totals["answer_sorry"] += 1
            elif decl["answer"] == "True":
                totals["answer_true"] += 1
            elif decl["answer"] == "False":
                totals["answer_false"] += 1

    summary = {
        "schema": SCHEMA,
        "catalog": {"commit": _git_head(root), "source": SOURCE_URL},
        "totals": {key: totals.get(key, 0) for key in (
            "files", "declarations", "research_open", "research_solved", "test",
            "textbook", "api", "other", "answer_sorry", "answer_true", "answer_false",
            "unmatched_attributes",
        )},
        "collections": [
            {
                "name": name,
                "files": counts["files"],
                "declarations": counts["declarations"],
                "research_open": counts["research_open"],
                "research_solved": counts["research_solved"],
            }
            for name, counts in sorted(per_collection.items())
        ],
        "files": files,
    }
    return summary


def _git_head(root: Path):
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _print_summary(scan: dict) -> None:
    print("formal-conjectures scan")
    commit = scan["catalog"]["commit"]
    print(f"  commit: {commit[:12] if commit else 'unknown'} ({scan['catalog']['source']})")
    for key in ("files", "declarations", "research_open", "research_solved",
                "answer_sorry", "unmatched_attributes"):
        print(f"  {key}: {scan['totals'][key]}")
    print(f"  collections: {len(scan['collections'])}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalog", help="path to a formal-conjectures checkout")
    parser.add_argument("--json", dest="json_path", help="write the scan data as JSON")
    args = parser.parse_args(argv)
    scan = scan_catalog(args.catalog)
    _print_summary(scan)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(scan, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
