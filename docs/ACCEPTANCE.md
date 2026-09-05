# 本地原型验收 · 2026-09-05

Windows 本机运行。测试数据放在隔离目录，日常数据库未写入测试偏好。桌面版是本项目独立实现；没有声称运行或集成 N.E.K.O.。

## 已验证

| 用户路径 | 证据 |
| --- | --- |
| 双击启动 | start.ps1 实际启动127.0.0.1:17861服务和Electron，页面显示已连接，密钥来自DPAPI |
| 桌宠小窗 | 实际Electron点击切换后outer约312×390，展开恢复原窗口；截图 desktop-compact.png |
| 真实模型与语音 | runtime-probe.json：真实chat/TTS/ASR、场景召回、更正删除及Codex读文件9项通过 |
| 浏览器播放和Stop | browser-probe.json：真实WebAudio自然播放ACK，中途stop实际调用音源stop，未播段不入历史，下一次真正模型输入只有已播放前缀 |
| 麦克风处理链路 | 合成中文音频作为MediaStream输入，走实际VAD→WAV上传→真实SenseVoice→聊天→自动记忆，7项浏览器验收通过 |
| 长期记忆 | 关闭并重新启动后端进程、新建会话，换说法召回工作饮品偏好；restart-probe.json |
| Codex暂停继续 | task-resume-probe.json：实际命令启动后中断，再恢复同一任务完成读文件，4项通过 |
| 对话自动派发任务 | tool-dispatch-probe.json：快速模型实际调用run_codex，Codex读出此前未知的新文件内容；没有只验证手动任务按钮 |
| 直播拥塞 | 自动测试注入1000条候选，缓冲100上限，取最近8个唯一话题、过期丢弃；当前播放中的新弹幕不取消当前turn |
| OBS | HTML及body透明；overlay-review.png角点Alpha=0；只转发live已确认字幕，私人场景不转发，观察窗口不ACK或重复播音 |
| 记忆可控 | 来源可查看；更正/忘记排除旧来源及旧助手内容；重复来源/重试不复活旧记忆；索引删除联动 |

核心自动测试：**84 passed, 8 subtests passed**。JavaScript入口语法检查通过。新增独立审查发现并修复了控制连接死亡后继续生成、排队TTS线程关闭后重启、记忆更正期间旧任务重新领取、关闭自动记忆后仍提交，以及自动更正后旧语音回写上下文的问题。

## 0.2 新增真实验收

| 路径 | 证据 |
| --- | --- |
| 词边界停止 | v2-probe.json：真实Windows引擎边界、浏览器输出进度、保留“我先”半段、实际下一次模型输入只有该前缀 |
| 主动任务通知 | v2-probe.json：真实Codex读取新文件完成后，私人空闲时自动播出结果 |
| 200条弹幕压力 | v2-probe.json：缓冲有界、只完成1轮短回复而不是200轮；28字上限，最新选中弹幕到播放969ms |
| 提取中强制退出 | memory-recovery-probe.json：真实请求processing时结束测试进程，重启自动接着保存；换说法召回，删除后再次重启不复活 |
| 同义与改口 | memory-reconciliation-probe.json：真实提取/合并，双来源同一canonical，明确咖啡改绿茶替换旧偏好，旧来源/助手对话失效，私人事实不进入直播 |
| 新版桌面 | desktop-v2-probe.json：实际Electron44.2.0小窗/展开、本地语音播放确认、记忆失败显示及重试、切页停止轮询、1920×1080直播画面8项通过 |

同义首次探针曾漏合并，导致更正后残留另一条旧偏好，原报告保留为 memory-reconciliation-first-failure.json。结构化记忆请求已改为temperature=0，后续样例通过；这不是任意语义和大规模记忆质量保证。

桌面依赖升级后npm审计为0项已知漏洞；新版Electron首次使用改为按需下载，启动器已补上对应安装步骤。新版实际Electron本地语音样例首字381ms、浏览器启动播放770ms。

## 测量边界

模型探针里Qwen3.5-35B-A3B三次短回复TTFT为569/520/501ms。浏览器真实音频链路的计时记录在 browser-probe.json；两次样例首字452/285ms、从接收消息到浏览器启动播放1166/1252ms。它是少量合成场景，**不是P95承诺，也不是物理扬声器开声测量**。后续复跑可能不同，保留报告中的实际值。

Windows本地音色支持引擎词边界和浏览器估计输出时钟，单次实测模型首字337ms、消息到浏览器启动播放728ms。云端CosyVoice2仍按完整短段确认；不猜测词时长。音频队列最多2段。以上均非物理声学测量。

召回使用Qwen3-Embedding-0.6B及关键词。真实中文换说法在.50余弦门槛下漏召回（.449），校准为.43后召回，选取的无关样例低于.40。样本很小，不能说明大规模记忆准确率；明确偏好改口有保守归并，复杂历史/多事实矛盾仍需手工核对。

暂停恢复验证的是只读文件任务；没有证明任意外部副作用的精确一次执行。真人麦克风、扬声器回声消除、真实直播平台弹幕/推流、Live2D Cubism仍未验收或未接入。

## 产物

报告和截图都在 `artifacts/`。测试源在 `tests/` 和 `probes/`。探针是合成任务和真实API调用，部分会消费模型请求；运行前应启动隔离测试服务17862，避免对日常记忆做清理测试。
# Live2D local acceptance (2026-09-05)

- `python probes/live2d.py`: seven checks passed in an isolated backend and Chromium with actual local SAPI audio. Model rendered, live RMS drove the observer mouth, private scene speech did not, Stop discarded pending audio and closed the observer mouth in 156 ms. Avatar switching propagated to the observer. No browser page errors.
- `python -m pytest -q`: 85 passed, 8 subtests passed. Added rejection tests for stale turn IDs, non-finite/out-of-range/string/bool mouth values and private mouth event filtering.
- Evidence: `artifacts/live2d-probe.json`, `artifacts/live2d-desktop.png`, `artifacts/live2d-stage.png`. The timing is browser-observed device-clock behavior, not a physical speaker measurement.
- An independent preview is running at http://127.0.0.1:17868/ with Live2D selected and local Huihui voice. Launch script: `probes/live2d_preview.py`; separate data under `artifacts/runtime-live2d-preview`. Automatic memory is disabled in this preview. Existing daily instance at port 17861 was preserved because automatic approval rejected its process restart.
- Bilibili title change, scene import, audio-track capture and public streaming remain unverified. No broadcast was started in this increment.
# Live2D optimization acceptance (2026-09-05)

- Fixed late observer joins and reconnects: live snapshots carry only the active turn ID and already-played prefix. Private snapshots carry neither. Mid-turn reload resumes mouth updates.
- Desktop uses portrait framing; stream overlay retains full-body framing. Resizing repaints immediately instead of waiting for a separate Pixi resize/ticker cycle. Compact screenshot inspection caught the transient blank canvas before the repair.
- `python probes/live2d.py`: 13 checks passed, including real TTS, mid-turn reload, compact repaint, played-prefix captions and actual next model context. Stop to observer mouth closure: 156 ms in this run. Evidence: `artifacts/live2d-optimized-probe.json`, `live2d-compact.png`, `live2d-desktop-optimized.png`, `live2d-stage-optimized.png`.
- `python -m pytest -q`: 86 passed, 8 subtests passed.
- Latest preview uses port 17869 with separate data and local Huihui voice. Launch with `python probes/live2d_preview.py --port 17869 --reload`. Earlier processes were preserved after automatic approval blocked stopping them.
