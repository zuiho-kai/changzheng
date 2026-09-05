"""Small, real provider probe. No credentials or private memory are persisted."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)
BASE = "https://api.siliconflow.cn/v1"
KEY = os.environ["SILICONFLOW_API_KEY"]
SESSION = requests.Session()
SESSION.headers.update({"Authorization": "Bearer " + KEY})
REPORT = {"at": datetime.now(timezone.utc).isoformat(), "base_url": BASE,
          "method": "Sequential short Chinese SSE requests; TTFT is first nonempty content delta, excluding reasoning. Not voice latency or a load test.", "results": []}


def save(row):
    REPORT["results"].append(row)
    (OUT / "siliconflow-probe.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False), flush=True)


def post(path, body):
    start = time.perf_counter()
    response = SESSION.post(BASE + path, json=body, timeout=(15, 60))
    response.raise_for_status()
    return response, round(time.perf_counter() - start, 3)


def chat(model, trial):
    start = time.perf_counter()
    first = None
    pieces = []
    finish = None
    done = False
    prompt = ["我今天有点累，想让你陪我聊两句。", "先别查资料了，陪我缓一会儿。", "等下我会让你做事，现在先随便聊聊。"][trial]
    body = {"model": model, "stream": True, "enable_thinking": False, "max_tokens": 100,
            "messages": [{"role": "system", "content": "你是中文个人陪伴助手。自然接话，只说一到两句、最多50字，不要列表，不要假装已执行任务。"},
                         {"role": "user", "content": prompt}]}
    with SESSION.post(BASE + "/chat/completions", json=body, stream=True, timeout=(15, 45)) as response:
        if response.status_code != 200:
            return {"kind": "chat", "model": model, "trial": trial + 1, "status": response.status_code,
                    "error": response.text[:300].replace(KEY, "[REDACTED]")}
        for line in response.iter_lines(chunk_size=1):
            if time.perf_counter() - start > 75:
                raise TimeoutError("overall stream deadline")
            if not line.startswith(b"data: "):
                continue
            payload = line[6:]
            if payload == b"[DONE]":
                done = True
                break
            msg = json.loads(payload)
            for choice in msg.get("choices", []):
                value = choice.get("delta", {}).get("content")
                if value:
                    first = first if first is not None else time.perf_counter() - start
                    pieces.append(value)
                finish = choice.get("finish_reason") or finish
    return {"kind": "chat", "model": model, "trial": trial + 1, "status": 200,
            "ttft_s": round(first, 3) if first is not None else None,
            "total_s": round(time.perf_counter() - start, 3), "text": "".join(pieces),
            "finish_reason": finish, "done": done}


def safe(kind, fn):
    try:
        save(fn())
    except Exception as exc:
        save({"kind": kind, "error": str(exc)[:350].replace(KEY, "[REDACTED]")})


models = ["Qwen/Qwen3.5-9B", "Qwen/Qwen3.5-35B-A3B", "inclusionAI/Ling-mini-2.0", "deepseek-ai/DeepSeek-V3.2"]
for trial in range(3):
    for model in models:
        safe("chat:" + model, lambda model=model, trial=trial: chat(model, trial))


def embeddings():
    response, elapsed = post("/embeddings", {"model": "Qwen/Qwen3-Embedding-0.6B", "input": ["用户工作时喜欢简短回复。", "直播时多和观众互动。"]})
    data = response.json()["data"]
    return {"kind": "embedding", "model": "Qwen/Qwen3-Embedding-0.6B", "status": response.status_code,
            "total_s": elapsed, "count": len(data), "dimensions": len(data[0]["embedding"])}


def rerank():
    response, elapsed = post("/rerank", {"model": "Qwen/Qwen3-Reranker-0.6B", "query": "帮我修改代码，回答怎么安排？",
        "documents": ["用户工作时喜欢简短回复并先说明结论。", "直播时多和观众互动。", "用户喜欢薄荷冰淇淋。"], "top_n": 3})
    return {"kind": "rerank", "model": "Qwen/Qwen3-Reranker-0.6B", "status": response.status_code,
            "total_s": elapsed, "ranking": response.json()["results"]}


safe("embedding", embeddings)
safe("rerank", rerank)
