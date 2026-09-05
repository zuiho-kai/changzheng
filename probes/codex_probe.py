"""App-server smoke test: actual file tool, interruption, process restart, history recall."""
import json
import queue
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
WORK = OUT / "codex-fixture"
WORK.mkdir(parents=True, exist_ok=True)
TOKEN = secrets.token_hex(8)
(WORK / "fixture.txt").write_text("Synthetic integration fixture.\nverification_word=" + TOKEN, encoding="utf-8")
REPORT = {"at": datetime.now(timezone.utc).isoformat(), "checks": []}


def save(row):
    REPORT["checks"].append(row)
    (OUT / "codex-probe.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False), flush=True)


class Server:
    def __init__(self):
        self.proc = subprocess.Popen([shutil.which("codex.exe") or "codex", "app-server", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.queue = queue.Queue()
        self.events = []
        self.seq = 0
        threading.Thread(target=self.read, daemon=True).start()
        self.call("initialize", {"clientInfo": {"name": "changzheng_probe", "version": "0.1.0"}})
        self.send({"method": "initialized", "params": {}})

    def read(self):
        for line in self.proc.stdout:
            try:
                self.queue.put(json.loads(line))
            except ValueError:
                pass
        self.queue.put({"method": "probe/processExited"})

    def send(self, value):
        self.proc.stdin.write(json.dumps(value) + "\n")
        self.proc.stdin.flush()

    def next(self, timeout):
        msg = self.queue.get(timeout=timeout)
        if msg.get("method") == "probe/processExited":
            raise RuntimeError("app-server exited")
        if "method" in msg and "id" in msg:
            # This probe does not grant new permissions or interact with external services.
            self.send({"id": msg["id"], "error": {"code": -32601, "message": "Probe client does not implement interactive requests"}})
        self.events.append(msg)
        return msg

    def call(self, method, params, timeout=60):
        self.seq += 1
        ident = self.seq
        self.send({"id": ident, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.next(max(.1, deadline - time.monotonic()))
            if msg.get("id") == ident and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"])[:600])
                return msg["result"]
        raise TimeoutError(method)

    def turn(self, thread_id, text, interrupt=False):
        offset = len(self.events)
        start = time.perf_counter()
        result = self.call("turn/start", {"threadId": thread_id, "effort": "low",
            "input": [{"type": "text", "text": text}]})
        turn_id = result["turn"]["id"]
        if interrupt:
            time.sleep(.4)
            self.call("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
        first = None
        deadline = time.monotonic() + 150
        cursor = offset
        while time.monotonic() < deadline:
            while cursor < len(self.events):
                msg = self.events[cursor]
                cursor += 1
                method, params = msg.get("method"), msg.get("params", {})
                if method == "item/agentMessage/delta" and first is None:
                    first = round(time.perf_counter() - start, 3)
                if method == "turn/completed" and params["turn"]["id"] == turn_id:
                    turn = params["turn"]
                    items = [x["params"]["item"] for x in self.events[offset:] if x.get("method") == "item/completed"]
                    messages = [x.get("text", "") for x in items if x.get("type") == "agentMessage"]
                    return {"status": turn["status"], "total_s": round(time.perf_counter() - start, 3),
                        "first_agent_delta_s": first, "messages": messages, "item_types": [x.get("type") for x in items],
                        "error": turn.get("error")}
            self.next(max(.1, deadline - time.monotonic()))
        raise TimeoutError("turn completion")

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=8)
        except (subprocess.TimeoutExpired, OSError):
            self.proc.terminate()
            self.proc.wait(timeout=8)


server = None
try:
    server = Server()
    models = server.call("model/list", {})
    defaults = [x["id"] for x in models.get("data", []) if x.get("isDefault")]
    save({"check": "initialize_model_list", "ok": True, "default_models": defaults})
    params = {"cwd": str(WORK), "approvalPolicy": "never", "sandbox": "read-only",
        "developerInstructions": "This is a narrow app-server integration probe. Only carry out the synthetic fixture instructions. Do not read private files, memories, accounts, or other projects. No external network, no delegation. Keep all answers minimal."}
    started = server.call("thread/start", params)
    tid = started["thread"]["id"]
    save({"check": "thread_start", "ok": True, "thread_id": tid, "model": started.get("model")})
    outcome = server.turn(tid, "Read fixture.txt in the working directory with a file-reading or shell tool. Return only its verification_word value. Do not modify files.")
    outcome.update({"check": "real_file_tool", "ok": TOKEN in " ".join(outcome["messages"]) and outcome["status"] == "completed"})
    save(outcome)
    interrupted = server.turn(tid, "Write a very long numbered list of 1000 fictional planet names. Do not use tools.", interrupt=True)
    interrupted.update({"check": "interrupt", "ok": interrupted["status"] == "interrupted"})
    save(interrupted)
    server.close()
    server = Server()
    resumed = server.call("thread/resume", {"threadId": tid})
    save({"check": "resume_after_process_restart", "ok": resumed["thread"]["id"] == tid})
    result = server.turn(tid, "Do not continue the planet list. Without reading any files or using tools, return only the verification_word you read earlier in this conversation.")
    result.update({"check": "history_recall_after_restart", "ok": TOKEN in " ".join(result["messages"]) and result["status"] == "completed"})
    save(result)
except Exception as exc:
    save({"check": "probe_error", "ok": False, "error": str(exc)[:700]})
finally:
    if server:
        server.close()
