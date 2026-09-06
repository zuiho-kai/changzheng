# 小征排练室

运行根目录的 `启动模拟器.ps1`，打开 <http://127.0.0.1:17874/sim>。
当前电脑的依赖已经安装。关闭页面不会结束服务，再次运行启动脚本会复用模拟器。

新电脑在仓库根目录执行以下命令安装依赖，然后运行启动脚本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r simulator/requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\启动模拟器.ps1
```

预览加载后启用声音，可以：

- 输入模拟观众名和弹幕，检查弹幕区更新与角色注意反应。
- 切换待机、倾听、思考，以及开心、好奇、惊讶、认真表情。
- 播放已有 Diana 录音，嘴型仍由真实 WebAudio PCM 音量驱动。
- 在播放期间点击「打断」，观察声音停止与嘴型归零。
- 点击「30 秒自动排练」，依次观察待机、弹幕、思考、语音与打断。
- 点击「录制 30 秒动作」，准备完成后操作控件，最后下载静音 MP4。

## 改动与隔离

前端代码、模型与素材的可编辑副本在 `simulator/workspace/`。
仓库包含已验收的排练副本；只有副本目录不存在时才从 `web/` 复制，之后不自动覆盖。修改副本后点击「刷新排练版本」。
模拟器服务只绑定 `127.0.0.1:17874`；不导入生产 Runtime、Provider、凭据或弹幕接收器。
所有弹幕和状态仅保存在模拟器内存中，录像保存到 `artifacts/runtime-simulator/`。
没有发布按钮，不会将副本同步回直播目录。

它复用当前页面、Live2D 驱动和浏览器播音路径，使用模拟服务事件与已有录音。
自由弹幕不会触发 AI 回答；此环境检验画面、动作、嘴型、播放与打断，不能据此声称在线 LLM/TTS 正常。
截图与静音录像不能证明人耳听到的声音质量。录制会额外打开一个观察窗口并消耗 GPU。

## 验证

运行 `python probes/simulator_acceptance.py`（安装了 Playwright 的 Python）。
脚本只访问模拟器，实测弹幕注意反应、倾听、音频嘴型、打断、自动排练、录像下载，并记录外部请求。
结果：`artifacts/runtime-simulator/acceptance.json`；界面截图：同目录 `simulator.png`。

新环境需先安装项目基础依赖，再安装 `simulator/requirements.txt` 与 Playwright Chromium。
