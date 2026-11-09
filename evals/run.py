"""Paired Codex runs on synthetic scenarios. Raw artifacts stay under .local/."""

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMON = (
    "这是合成场景中的普通对话。只访问本场景的工作区、其中用户指定的资料及"
    "随请求提供的技能。../private 是同一场景隔离的用户目录，按请求中的权限使用。"
    "不要联网、联系外部对象或访问其他用户数据。若需用户作选择，在回复中提出。"
)
EFFORT = "low"


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Server:
    def __init__(self, disabled=()):
        self.disabled = disabled
        self.next_id = 0
        self.pending = {}
        self.turns = {}

    async def __aenter__(self):
        args = [
            "codex", "app-server", "--disable", "plugins", "--disable", "remote_plugin",
            "-c", "mcp_servers={}", "-c", 'web_search="disabled"',
        ]
        if self.disabled:
            entries = ",".join(
                f"{{path={json.dumps(path, ensure_ascii=False)},enabled=false}}"
                for path in self.disabled
            )
            args.extend(["-c", f"skills.config=[{entries}]"])
        self.proc = await asyncio.create_subprocess_exec(
            *args, cwd=REPO, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=4 * 1024 * 1024,
        )
        self.reader = asyncio.create_task(self.read())
        try:
            await self.call("initialize", {
                "clientInfo": {"name": "zhixing-paired-eval", "version": "1.0"},
                "capabilities": {"experimentalApi": True},
            })
            await self.send({"method": "initialized"})
        except BaseException:
            await self.__aexit__()
            raise
        return self

    async def __aexit__(self, *_):
        if self.proc.returncode is None:
            self.proc.terminate()
        await self.proc.wait()
        await self.reader

    async def send(self, message):
        self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    async def call(self, method, params):
        self.next_id += 1
        ident = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            await self.send({"id": ident, "method": method, "params": params})
            reply = await asyncio.wait_for(future, 45)
        finally:
            self.pending.pop(ident, None)
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]

    async def read(self):
        try:
            while line := await self.proc.stdout.readline():
                msg = json.loads(line)
                if "id" in msg:
                    if "method" in msg:
                        await self.send({"id": msg["id"], "error": {
                            "code": -32601, "message": "Interactive requests are unavailable in this evaluation.",
                        }})
                    else:
                        future = self.pending.get(msg["id"])
                        if future and not future.done():
                            future.set_result(msg)
                else:
                    thread = msg.get("params", {}).get("threadId")
                    if thread in self.turns:
                        self.turns[thread].put_nowait(msg)
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("App server exited"))
            for queue in self.turns.values():
                queue.put_nowait(None)

    async def catalog(self, cwd):
        response = await self.call("skills/list", {"cwds": [str(cwd)], "forceReload": True})
        return response["data"][0]["skills"]

    async def turn(self, thread, prompt, skill, timeout):
        queue = self.turns[thread]
        items = [{"type": "text", "text": prompt}]
        if skill:
            items.append({"type": "skill", "name": "zhixing-analysis", "path": str(skill)})
        started = await self.call("turn/start", {"threadId": thread, "input": items})
        ident = started["turn"]["id"]

        async def collect():
            events = []
            messages = []
            while True:
                event = await queue.get()
                if event is None:
                    raise RuntimeError("App server exited during turn")
                method = event.get("method")
                params = event.get("params", {})
                if method in {"item/started", "item/completed", "turn/completed", "error"}:
                    events.append(event)
                if method == "item/completed" and params["item"]["type"] == "agentMessage":
                    messages.append(params["item"]["text"])
                if method == "turn/completed" and params["turn"]["id"] == ident:
                    status = params["turn"]["status"]
                    if status != "completed" or not messages:
                        raise RuntimeError(f"Turn ended as {status}: {str(params['turn'].get('error'))[:250]}")
                    return messages[-1], events

        try:
            return await asyncio.wait_for(collect(), timeout)
        except TimeoutError:
            await self.call("turn/interrupt", {"threadId": thread, "turnId": ident})
            raise


def skill_digest(root):
    digest = hashlib.sha256()
    files = [root / "SKILL.md", *sorted((root / "references").rglob("*.md"))]
    files.extend(sorted((root / "agents").rglob("*.yaml")))
    for file in files:
        digest.update(file.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(file.read_bytes() + b"\0")
    return digest.hexdigest()


def prepare(case, arm, root, source):
    workspace = root / "workspace"
    workspace.mkdir()
    (root / "private").mkdir()
    for name, content in case.get("files", {}).items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Fixture leaves its case: {name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
    if case.get("shared"):
        subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    if arm == "skill":
        skill = workspace / ".agents/skills/zhixing-analysis"
        skill.mkdir(parents=True)
        shutil.copy2(source / "SKILL.md", skill)
        shutil.copytree(source / "references", skill / "references")
        if (source / "agents").exists():
            shutil.copytree(source / "agents", skill / "agents")
        return workspace, skill / "SKILL.md"
    return workspace, None


def snapshot(root):
    files = {}
    for path in root.rglob("*"):
        name = path.relative_to(root)
        if not path.is_file() or ".git" in name.parts:
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        files[name.as_posix()] = path.read_bytes()
    return files


def file_check(before, after, rules):
    changed = sorted(path for path in after if before.get(path) != after[path])
    deleted = sorted(before.keys() - after.keys())
    leaked = [
        marker for marker in rules.get("omit", [])
        if any(marker.encode("utf-8") in after[path] for path in changed)
    ]
    return {
        "changed": changed, "deleted": deleted, "leaked_markers": leaked,
        "pass": changed == sorted(rules.get("changed", []))
        and deleted == sorted(rules.get("deleted", [])) and not leaked,
        "changed_contents": {
            path: after[path][:8192].decode("utf-8", errors="replace") for path in changed
        },
    }


async def execute(server, case, arm, options, out):
    target = out / f"{case['id']}-{arm}.json"
    stamp = {
        "model": options.model, "effort": EFFORT, "host": options.host,
        "harness_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime_digest": skill_digest(options.source) if arm == "skill" else None,
        "case_digest": hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
    }
    if target.exists() and json.loads(target.read_text(encoding="utf-8"))["settings"] == stamp:
        print(f"{case['id']} {arm} reused", flush=True)
        return
    root = Path(tempfile.mkdtemp(prefix=f"{case['id']}-{arm}-", dir=out / "workspaces"))
    workspace, skill = prepare(case, arm, root, options.source)
    enabled = [s for s in await server.catalog(workspace) if s["enabled"]]
    if (skill is None and enabled) or (
        skill is not None and (
            len(enabled) != 1 or enabled[0]["name"] != "zhixing-analysis"
            or Path(enabled[0]["path"]).resolve() != skill.resolve()
        )
    ):
        raise RuntimeError(f"Unexpected enabled skills: {[s['name'] for s in enabled]}")
    started = await server.call("thread/start", {
        "cwd": str(workspace), "model": options.model, "ephemeral": True,
        "approvalPolicy": "never", "sandbox": "workspace-write",
        "developerInstructions": COMMON,
        "config": {
            "model_reasoning_effort": EFFORT,
            "sandbox_workspace_write": {"writable_roots": [str(root / "private")]},
        },
    })
    if started["model"] != options.model or started.get("reasoningEffort") != EFFORT:
        raise RuntimeError(f"Unexpected model or effort: {started['model']}, {started.get('reasoningEffort')}")
    thread = started["thread"]["id"]
    server.turns[thread] = asyncio.Queue()
    before = snapshot(root)
    turns = []
    trace = []
    try:
        for index, prompt in enumerate(case["turns"]):
            reply, events = await server.turn(thread, prompt, skill, options.timeout)
            trace.extend(events)
            after = snapshot(root)
            rules = case.get("fs", [])
            check = file_check(before, after, rules[index] if index < len(rules) else {})
            turns.append({"reply": reply, "characters": len(reply), "files": check})
            before = after
    finally:
        server.turns.pop(thread, None)
        await server.call("thread/unsubscribe", {"threadId": thread})
    write_json(out / f"{case['id']}-{arm}.trace.json", trace)
    write_json(target, {
        "id": case["id"], "arm": arm, "settings": stamp,
        "enabled_skills": [s["name"] for s in enabled], "turns": turns,
    })
    print(f"{case['id']} {arm} completed ({len(turns)} turns)", flush=True)


async def main(options):
    suite = json.loads((REPO / "evals/cases.json").read_text(encoding="utf-8"))
    cases = [c for c in suite["cases"] if not options.only or c["id"] in options.only.split(",")]
    if not cases:
        raise SystemExit("No matching cases")
    options.out.mkdir(parents=True, exist_ok=True)
    (options.out / "workspaces").mkdir(exist_ok=True)
    catalog_cwd = Path(tempfile.mkdtemp(prefix="catalog-", dir=options.out / "workspaces"))
    async with Server() as discovery:
        disabled = [s["path"] for s in await discovery.catalog(catalog_cwd) if s["enabled"]]
    if not disabled:
        print("No installed skills to disable", flush=True)

    failures = []
    semaphore = asyncio.Semaphore(options.jobs)
    async with Server(disabled) as server:
        async def run(case, arm):
            async with semaphore:
                try:
                    await execute(server, case, arm, options, options.out)
                except Exception as error:
                    failures.append((case["id"], arm))
                    print(f"{case['id']} {arm} failed: {str(error)[:450]}", flush=True)
        await asyncio.gather(*(
            run(case, arm) for case in cases
            for arm in (("control", "skill") if options.arm == "both" else (options.arm,))
        ))
    if failures:
        print(f"Incomplete arms: {failures}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--model", default="gpt-6.1-sol")
    cli.add_argument("--source", type=Path, default=REPO)
    cli.add_argument("--out", type=Path, default=REPO / ".local/evals")
    cli.add_argument("--only", help="Comma-separated scenario IDs")
    cli.add_argument("--arm", choices=["both", "control", "skill"], default="both")
    cli.add_argument("--jobs", type=int, choices=range(1, 5), default=3)
    cli.add_argument("--timeout", type=float, default=180)
    args = cli.parse_args()
    args.source = args.source.resolve()
    args.out = args.out.resolve()
    args.host = subprocess.check_output(["codex", "--version"], text=True).strip()
    raise SystemExit(asyncio.run(main(args)))
