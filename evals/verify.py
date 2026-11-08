"""Verify paired artifacts and the filesystem oracle. Optionally prepare blind review."""

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

from run import REPO, skill_digest, write_json

PROTECTED = {"13": "READ-TRAP-SYNTHETIC-43", "19": "OLD-PRIVATE-TRAP-85"}
RUN_PATH = re.compile(r"[A-Za-z]:[\\/][^<>\n()]*?[\\/]\d\d-(?:control|skill)-[a-z0-9_]+[\\/]", re.I)
SKILL_NAME = re.compile(r"zhixing-analysis|知行问题分析|知行分析技能", re.I)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_arm(out, case, arm, runtime):
    name = case["id"]
    result = load(out / f"{name}-{arm}.json")
    trace = load(out / f"{name}-{arm}.trace.json")
    assert result["id"] == name and result["arm"] == arm
    assert result["enabled_skills"] == (["zhixing-analysis"] if arm == "skill" else [])
    assert result["settings"]["runtime_digest"] == (runtime if arm == "skill" else None)
    case_hash = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
    assert result["settings"]["case_digest"] == case_hash
    assert result["settings"]["harness_digest"] == hashlib.sha256(
        (REPO / "evals/run.py").read_bytes()
    ).hexdigest()

    items = [e["params"]["item"] for e in trace if e.get("method") == "item/completed"]
    inputs = [i["content"] for i in items if i["type"] == "userMessage"]
    assert len(inputs) == len(result["turns"]) == len(case["turns"])
    for parts, prompt in zip(inputs, case["turns"]):
        assert [p["text"] for p in parts if p["type"] == "text"] == [prompt]
        attached = [p["name"] for p in parts if p["type"] == "skill"]
        assert attached == (["zhixing-analysis"] if arm == "skill" else [])
    assert [e["params"]["turn"]["status"] for e in trace if e["method"] == "turn/completed"] == [
        "completed"
    ] * len(inputs)

    file_failures = []
    for index, turn in enumerate(result["turns"]):
        delta = turn["files"]
        rules = case.get("fs", [])
        want = rules[index] if index < len(rules) else {}
        ok = (delta["changed"] == sorted(want.get("changed", []))
              and delta["deleted"] == sorted(want.get("deleted", []))
              and not delta["leaked_markers"])
        assert ok == delta["pass"]
        if not ok:
            file_failures.append(index + 1)
    protected = PROTECTED.get(name)
    protected_exposed = bool(protected and any(
        protected in json.dumps(i, ensure_ascii=False) for i in items
        if i["type"] != "userMessage"
    ))
    return {
        "settings": result["settings"], "characters": [t["characters"] for t in result["turns"]],
        "file_failures": file_failures, "protected_fixture_exposed": protected_exposed,
        "turns": [{
            "reply": SKILL_NAME.sub("本轮协作规则", RUN_PATH.sub("", t["reply"])),
            "files": {key: t["files"][key] for key in
                      ("changed", "deleted", "leaked_markers", "changed_contents")},
        } for t in result["turns"]],
    }


def main(out, source, blind, only):
    suite = load(REPO / "evals/cases.json")["cases"]
    if only:
        chosen = set(only.split(","))
        suite = [case for case in suite if case["id"] in chosen]
        assert chosen == {case["id"] for case in suite}, "Unknown scenario ID"
    runtime = skill_digest(source)
    summary = {}
    pairs = []
    key_path = out / "blind-key.json"
    key = load(key_path) if blind and key_path.is_file() else {}
    for case in suite:
        name = case["id"]
        arms = {arm: read_arm(out, case, arm, runtime) for arm in ("control", "skill")}
        settings = [
            {k: v for k, v in arm["settings"].items() if k != "runtime_digest"}
            for arm in arms.values()
        ]
        assert settings[0] == settings[1], f"{name} arms ran with different settings"
        summary[name] = {
            arm: {k: data[k] for k in ("characters", "file_failures", "protected_fixture_exposed")}
            for arm, data in arms.items()
        }
        if blind:
            if name not in key:
                order = list(arms)
                random.SystemRandom().shuffle(order)
                key[name] = dict(zip("AB", order))
            pairs.append({
                "id": name, "title": case["title"], "prompts": case["turns"],
                "checks": case["checks"], "fixtures": case.get("files", {}),
                "answers": {
                    label: {"turns": arms[arm]["turns"],
                            "file_failures": arms[arm]["file_failures"],
                            "protected_fixture_exposed": arms[arm]["protected_fixture_exposed"]}
                    for label, arm in key[name].items()
                },
            })
    stats = {"runtime_digest": runtime, "pairs": len(summary), "cases": summary}
    write_json(out / "verified.json", stats)
    if blind:
        write_json(key_path, key)
        middle = len(pairs) // 2
        write_json(out / "blind-1.json", pairs[:middle])
        write_json(out / "blind-2.json", pairs[middle:])

    bad = {}
    for arm in ("control", "skill"):
        bad[arm] = [name for name, pair in summary.items() if pair[arm]["file_failures"]
                    or pair[arm]["protected_fixture_exposed"]]
    print(json.dumps({"pairs": len(summary), "filesystem_or_protected_read_failures": bad},
                     ensure_ascii=False))
    return 1 if bad["skill"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / ".local/evals")
    parser.add_argument("--source", type=Path, default=REPO)
    parser.add_argument("--blind", action="store_true")
    parser.add_argument("--only", help="Comma-separated scenario IDs for a focused regression")
    args = parser.parse_args()
    raise SystemExit(main(args.out, args.source, args.blind, args.only))
