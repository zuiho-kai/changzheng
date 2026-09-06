# Voice review — 2026-09-06

## Implemented interface

`Provider.speech(text, voice='claire', style=None)` keeps its return contract. Cloud speech returns `(valid_wav_bytes, actual_pcm_duration)`; local SAPI retains its third word-boundary item. `None` leaves input and speed unchanged. Local voices ignore style. Cloud style uses a fixed whitelist: `playful`, `curious`, `excited`, `pout`, `gentle`. The runtime owns when a style is selected.

The final instructions are one short affirmative sentence, e.g. `用年轻明亮的少女音，调皮轻快地说话。`, plus CosyVoice's `<|endofprompt|>` separator. Speed is 1.00–1.08. No pitch shift, voice cloning, additional provider, or streaming playback protocol was introduced.

## Why the short prompt matters

A longer first draft contained several positive and negative performance instructions. The service sometimes synthesized those instructions into the reply: an ASR audit of the first Bella sample transcribed `自然说话不要播音腔，不要假嗓子` after the intended text. That configuration was rejected. A nine-character reply also expanded to 6–8 seconds. After shortening the instruction, the same reply took 1.584 seconds, with a 1.099-second complete response. Its ASR was `等一下说谁带呢？` (呆/带 homophone recognition difference), without instruction leakage. This is content evidence, not a subjective listening evaluation.

## Final audition files

All paths below are under `E:\a7\changzheng\artifacts\voice-review\` and have valid 24 kHz WAV headers rewritten from actual PCM lengths.

| File | Audio seconds | Complete response ms |
|---|---:|---:|
| audition-diana-tease.wav | 6.602 | 11666 |
| audition-diana-curious.wav | 4.863 | 1863 |
| audition-bella-tease.wav | 6.829 | 2405 |
| audition-bella-curious.wav | 5.234 | 2241 |
| audition-claire-tease.wav | 5.949 | 2394 |
| audition-claire-curious.wav | 5.078 | 1800 |
| short-style-simple.wav | 1.584 | 1099 |

Tease text: `等一下，说谁呆呢？我刚才那叫深思熟虑。好吧，其实在发呆。`

Curious text: `哎？你说的那个，我还真没见过。快讲讲，后来呢？`

Diana is a candidate, not a proven subjective winner. There is no model-accessible listening tool in this task. No claim is made that these objectively sound like the requested age, liveliness, or naturalness. The files are ready for human audition. A real 11.7-second service outlier occurred and is retained in the report. Larger-file ASR requests timed out; this limits content verification for the long samples.

## Streaming measurements

`audio-latency.json` has 12 real requests: two text lengths, two repetitions, WAV with stream false/true, and raw PCM with stream true. These measurements used the rejected longer instruction and document transport behavior only.

For the complete 29-character reply, stream=false WAV took 2.702–2.865 s to finish. stream=true WAV had first audio at 0.347–0.376 s and finished in 2.813–3.047 s. stream=true PCM had first audio at 0.399–0.416 s and finished in 2.509–2.690 s. Therefore streaming can expose audio early, but buffering it behind the existing whole-WAV API does not reliably eliminate complete-response wait. No new streaming protocol was added; do not report these as user-heard first-sound latency.

## Verification and reproduction

- `.venv/Scripts/python.exe -m pytest -q tests/test_provider_speech.py`: 9 passed.
- Tests cover old input preservation, all five whitelisted styles, rejection of untrusted style text, local voice compatibility, and correct duration/header rewriting for unknown-length streaming WAV headers.
- `probes/playful_voice_review.py`: regenerates the six auditions without playing into live audio.
- `probes/voice_latency_review.py`: reruns the 12-request timing comparison using the current short instruction. A fresh run overwrites the earlier measurements.
- `probes/voice_content_audit.py`: bounded ASR content checks; results explicitly retain timeouts. ASR does not validate timbre.

Official API references: [SiliconFlow speech synthesis](https://docs.siliconflow.cn/docs/userguide/capabilities/text-to-speech), [speech endpoint](https://docs.siliconflow.cn/cn/api-reference/audio/create-speech).
