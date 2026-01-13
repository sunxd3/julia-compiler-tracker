#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Iterable, List

DEFAULT_COMPILER_PATHS = [
    "src/",
    "compiler/",
    "base/compiler/",
    "base/inference/",
    "base/ircode/",
    "base/ast/",
    "base/optimizer/",
]

PR_PATTERN = re.compile(r"\(#(\d+)\)")


@dataclass
class CommitRecord:
    sha: str
    author: str
    date: str
    subject: str
    pr_number: str
    files: List[str]


def run_git_log(repo: str, start: str, end: str) -> str:
    cmd = [
        "git",
        "-C",
        repo,
        "log",
        "--name-only",
        "--date=iso-strict",
        f"{start}..{end}",
        "--pretty=format:%x1e%H%x1f%an%x1f%ad%x1f%s",
    ]
    return subprocess.check_output(cmd, text=True)


def parse_git_log(raw: str) -> Iterable[CommitRecord]:
    for block in raw.strip("\n\x1e").split("\x1e"):
        if not block.strip():
            continue
        header, *files = block.strip("\n").split("\n")
        header_parts = header.split("\x1f")
        if len(header_parts) != 4:
            continue
        sha, author, date, subject = header_parts
        pr_match = PR_PATTERN.search(subject)
        pr_number = pr_match.group(1) if pr_match else ""
        cleaned_files = [file for file in files if file.strip()]
        yield CommitRecord(
            sha=sha,
            author=author,
            date=date,
            subject=subject,
            pr_number=pr_number,
            files=cleaned_files,
        )


def is_compiler_related(files: Iterable[str], paths: Iterable[str]) -> bool:
    for file in files:
        for path in paths:
            if file.startswith(path):
                return True
    return False


def write_json(records: Iterable[CommitRecord], output_path: str) -> None:
    payload = [
        {
            "sha": record.sha,
            "author": record.author,
            "date": record.date,
            "subject": record.subject,
            "pr_number": record.pr_number,
            "files": record.files,
        }
        for record in records
    ]
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def write_csv(records: Iterable[CommitRecord], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sha",
                "author",
                "date",
                "subject",
                "pr_number",
                "files",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "sha": record.sha,
                    "author": record.author,
                    "date": record.date,
                    "subject": record.subject,
                    "pr_number": record.pr_number,
                    "files": ";".join(record.files),
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Julia compiler-related commits between tags.",
    )
    parser.add_argument("--repo", required=True, help="Path to Julia repo")
    parser.add_argument("--start-tag", required=True, help="Start tag")
    parser.add_argument("--end-tag", required=True, help="End tag")
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (.json or .csv)",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=DEFAULT_COMPILER_PATHS,
        help="Compiler-related paths to filter",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not os.path.isdir(args.repo):
        raise SystemExit(f"Repo path not found: {args.repo}")

    raw_log = run_git_log(args.repo, args.start_tag, args.end_tag)
    records = [
        record
        for record in parse_git_log(raw_log)
        if is_compiler_related(record.files, args.paths)
    ]

    output_path = args.output
    if output_path.endswith(".json"):
        write_json(records, output_path)
    elif output_path.endswith(".csv"):
        write_csv(records, output_path)
    else:
        raise SystemExit("Output file must end with .json or .csv")

    print(f"Wrote {len(records)} records to {output_path}")


if __name__ == "__main__":
    main()
