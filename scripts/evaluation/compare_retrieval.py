"""Compare a Git baseline with the checkout on identical private English evidence.

Fixtures never touch services. --hosted performs stateless Pinecone inference and
index metadata reads only; it does not query/upsert any production vectors.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hosted", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.baseline + "^{commit}"], text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive = output / "baseline.zip"
    subprocess.run(["git", "archive", "--format=zip", baseline, "-o", str(archive)], check=True)
    old = output / "baseline-source"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(old)
    # Explicit transport-only control, including legacy END truncation. Neither
    # ranking nor chunking is substituted in the archived baseline.
    shutil.copyfile(
        root / "scripts/evaluation/legacy_transport.py",
        old / "scripts/evaluation/legacy_transport.py",
    )
    dataset = root / "services/evaluation/datasets/ajg_sop_benchmark.jsonl"
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    english = output / "english.jsonl"
    english.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cases if c["language"] == "english"),
        encoding="utf-8",
    )
    runtime = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ["apps/api", "services", "packages"]
        for p in (root / folder).rglob("*.py")
        if "__pycache__" not in str(p)
    }
    provenance = {
        "baseline_commit": baseline,
        "checkout_commit": head,
        "checkout_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "baseline_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(english.read_bytes()).hexdigest(),
        "corpus": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.corpus_dir.glob("*.md")
        },
        "runtime_sha256": runtime,
        "hosted": args.hosted,
        "baseline_transport_shim": args.hosted,
    }
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    failed = False
    for label, cwd in [("baseline", old), ("integrated", root)]:
        embedding = (
            (
                "plugin:scripts.evaluation.legacy_transport:build_baseline_e5"
                if label == "baseline"
                else "pinecone-e5"
            )
            if args.hosted
            else "fixture-hash"
        )
        configs = [
            {
                "name": "token-overlap",
                "embedding": embedding,
                "reranker": "fixture",
                "assistant": not args.hosted,
            },
            {
                "name": "preserve-fusion",
                "embedding": embedding,
                "reranker": "none",
                "assistant": not args.hosted,
            },
        ]
        if not args.hosted:
            configs.extend(
                [
                    {"name": "lexical-only", "semantic": False, "reranker": "none"},
                    {"name": "semantic-only", "lexical": False, "reranker": "none"},
                ]
            )
        matrix = output / (label + "-matrix.json")
        matrix.write_text(
            json.dumps({"ks": [1, 3, 5, 10], "primary_k": 5, "configs": configs}), encoding="utf-8"
        )
        env = dict(
            os.environ,
            APP_MODE="fixture",
            LLM_PROVIDER="fixture",
            APP_NAME="Aziz Jan Group SOP Knowledge System",
            PYTHONUTF8="1",
            PYTHONPATH=str(cwd),
        )
        result_dir = output / label
        command = [
            sys.executable,
            "-m",
            "scripts.evaluation.run_benchmark",
            "--corpus-dir",
            str(args.corpus_dir.resolve()),
            "--dataset",
            str(english),
            "--matrix",
            str(matrix),
            "--output-dir",
            str(result_dir),
        ]
        with (output / (label + ".log")).open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        result = result_dir / "results.json"
        if result.exists():
            data = json.loads(result.read_text(encoding="utf-8"))
            # The archived directory has no .git. Correct the runner's parent
            # checkout lookup using the explicitly resolved archive provenance.
            reported_commit = data["git_commit"]
            data["git_commit"] = baseline if label == "baseline" else head
            result.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report = result_dir / "report.md"
            if report.exists():
                report.write_text(
                    report.read_text(encoding="utf-8").replace(
                        f"- Commit: `{reported_commit}`", f"- Commit: `{data['git_commit']}`"
                    ),
                    encoding="utf-8",
                )
            print(
                json.dumps(
                    {
                        "run": label,
                        "source_commit": data["git_commit"],
                        "status": [(c["name"], c["status"]) for c in data["configs"]],
                    }
                ),
                flush=True,
            )
        failed = failed or completed.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
