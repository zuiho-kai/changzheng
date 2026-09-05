"""Synthetic TTS audio and optional ASR roundtrip, not a microphone/barge-in test."""
import io
import json
import os
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1] / "artifacts"
OUT.mkdir(exist_ok=True)
KEY = os.environ["SILICONFLOW_API_KEY"]
SESSION = requests.Session()
SESSION.headers.update({"Authorization": "Bearer " + KEY})
BASE = "https://api.siliconflow.cn/v1"
report = {"at": datetime.now(timezone.utc).isoformat(), "checks": []}


def save(row):
    report["checks"].append(row)
    (OUT / "voice-probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False), flush=True)


try:
    model_response = SESSION.get(BASE + "/models", timeout=(15, 30))
    model_response.raise_for_status()
    asr_models = [m["id"] for m in model_response.json()["data"] if "sensevoice" in m["id"].lower()]
    save({"check": "asr_model_discovery", "models": asr_models})
    start = time.perf_counter()
    first = None
    data = bytearray()
    body = {"model": "FunAudioLLM/CosyVoice2-0.5B", "voice": "FunAudioLLM/CosyVoice2-0.5B:claire",
            "input": "我在呢，你可以随时打断我。等你说完，我们再继续刚才的事情。", "response_format": "wav", "stream": True}
    with SESSION.post(BASE + "/audio/speech", json=body, stream=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                if first is None:
                    first = time.perf_counter() - start
                data.extend(chunk)
    (OUT / "voice-sample-stream.wav").write_bytes(data)
    with wave.open(io.BytesIO(data), "rb") as wav:
        # Streaming WAV may advertise 0xffffffff data bytes. Count received PCM,
        # then write a normal finalized WAV so players show the actual duration.
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        pcm = wav.readframes(wav.getnframes())
    with wave.open(str(OUT / "voice-sample.wav"), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    audio_meta = {"sample_rate": rate, "channels": channels,
                  "duration_s": round(len(pcm) / (rate * channels * width), 3)}
    save({"check": "tts", "ok": True, "model": body["model"], "voice": body["voice"],
          "first_1024_bytes_s": round(first, 3), "total_s": round(time.perf_counter() - start, 3),
          "bytes": len(data), "audio": audio_meta, "file": "artifacts/voice-sample.wav",
          "note": "First network chunk can include WAV header; not measured speaker onset. The utterance describes target behavior, not implemented functionality."})
    if asr_models:
        model = next((m for m in asr_models if not m.startswith("Pro/")), asr_models[0])
        start = time.perf_counter()
        response = SESSION.post(BASE + "/audio/transcriptions", data={"model": model},
            files={"file": ("voice-sample.wav", (OUT / "voice-sample.wav").read_bytes(), "audio/wav")}, timeout=(15, 60))
        response.raise_for_status()
        save({"check": "synthetic_audio_asr", "ok": True, "model": model,
            "total_s": round(time.perf_counter() - start, 3), "text": response.json().get("text"),
            "note": "Recognition of synthesized audio; no real microphone, echo cancellation, or interruption test."})
except Exception as exc:
    save({"check": "error", "ok": False, "error": str(exc)[:400].replace(KEY, "[REDACTED]")})
