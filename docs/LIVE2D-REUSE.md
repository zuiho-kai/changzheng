# Live2D 制作与调校复用笔记

记录时间：2026-09-05。适用项目：`E:\a7\changzheng`。下次接手先读本页，再看 [当前表情绑定](EXPRESSION-RIG.md)；[手工绑定试作](MANUAL-RIG.md) 和 [2000 模型分析](REFERENCE-RIG-2000.md) 是历史，不要把其中未完成的转头路线当成当前任务。

## 先记住这几条

1. 用户要的是在实际直播画面里可见、自然、有表现力的角色。二进制可加载、参数有变化、截图不为空、测试全绿，都不能单独证明动作好看。
2. 先做可看的纵向成果：保留角色身份和画风，保证脸部清晰，做好眉眼口型与姿势。用户已明确暂停大角度左右转头，不要自行重启侧脸工程。
3. “太机器、幅度太小”不是继续叠几条低幅正弦曲线。此次有效调整是明确的姿势目标、不等长停留、头先动、身体跟随、发梢延迟和轻微回弹。
4. 模型形态和运行时表演是两层。只拿 `.moc3`/`.model3.json` 去别的软件，不会自动带走网页中的整套待机、状态与音频驱动。
5. 参考 Neuro 的可观察动作，不能声称复现其内部算法。参考片段有剪辑和镜头缩放，要看头相对身体的运动。

## 当前可复用资产

| 用途 | 项目内路径 | 说明 |
| --- | --- | --- |
| 活动模型入口 | `web/models/changzheng/model.model3.json` | 以这里实际引用的 MOC、贴图、表情和动作文件为准 |
| 当前构建脚本 | `probes/build_expression_rig.py` | 正面表情模型，11 网格、17 参数 |
| 低层封装依赖 | `.reference/image2live2d-research/src` | `moc3_emit`、`moc3_binary`；换机器时单独检查，不能假定普通 clone 自带 |
| 构建输出 | `artifacts/runtime-expression-rig/bundle` | 构建不会自动部署到活动模型目录 |
| 对齐的源素材 | `artifacts/changzheng-manual-assets/` | `source.png`、`blank.png`、`expression.png`、`surprised.png`，均为 1254×1254 |
| 待机与状态驱动 | `web/avatar-performance.js` | `AvatarPerformance`；姿势、弹簧、表情、眨眼和手势 |
| 播放器集成 | `web/live2d.js` | `beforeModelUpdate` 写参数、取景、父页面事件和口型超时 |
| 对话状态与停止 | `web/app.js` | 把生产状态和真实播放口型送给模型；重载后重新同步 |
| 完整直播画面 | `web/stage.html` | `/stage`；角色、背景和公开字幕 |
| 透明观察画面 | `/overlay` | 不自行重复播放音频；声音来自主控制端 |
| 动作前后对照 | `web/motion-review.html` | `/static/motion-review.html`，依赖 `web/assets/motion-demo/` 中的录像 |

模型目录有早期遗留的动作、物理与配置文件；文件存在不代表被当前入口引用。例如当前 `model.model3.json` 没有引用 `model.physics3.json`。不要仅凭目录清单宣布具备某项物理或动作能力。

`artifacts/changzheng-expression-live2d.zip` 和 `changzheng-expression-source.zip` 生成于最新大幅待机调整之前，不能直接当作最新版交付。需要分发时从当前素材、脚本、活动模型和网页驱动重新组包，并核对包内文件。

## 素材与绑定：有效做法和失败原因

- 优先检查最终画面中脸的实际像素。早期拆层后面部只有约 86 px；改用高分辨率半身素材后约 250 px，线条才有足够预算。2048 的图集不能恢复原素材缺失的五官细节。
- AI 编辑素材必须保持同一画布、同一头位、同一发际线和服装。分别准备原画、无五官脸底、闭眼/张嘴素材、惊讶眼睛，再机械提取局部区域。请求 1536 不等于实际返回 1536；本次实际均是 1254，脚本要检查真实尺寸。
- 本次用了洋红底色键，需同时处理透明度与银发边缘残色；仅删除纯色像素会留下彩边。提示词和实际来源见 `MANUAL-RIG.md`、`EXPRESSION-RIG.md`。
- 眉、眼、嘴用局部网格；所有面部补片共享头、颈、身体的全局变换，局部表情再叠加。否则歪头时会出现五官滑动和接缝。
- 低层写 MOC3 时，本实现坐标使用 Y 向下；多参数关键形态的第一个绑定参数变化最快。构建脚本用逆序 `itertools.product` 并按同样逆序映射参数。写反会出现单参数看似正常、组合姿势错乱。
- 统一底图位移和浅椭球投影没能做出合格侧脸。大角度转头需要拆开脸轮廓、眼鼻口、前后发和颈部，补遮挡，并逐部件制作左右上下及四角形态。物理和平滑不能补出缺失的侧脸。
- 本次制作不经过 Cubism 编辑器，没有 `.cmo3` 工程。源码、对齐 PNG 和构建依赖才是可重建来源；运行时 `.moc3` 不是编辑工程。

## 当前动作基线：先复用，再看画面调整

早期“轻晃＋慢速正弦”的版本被用户明确认为机械且不明显。当前实现把正弦降为细微呼吸，主运动改为六组姿势目标。

| 项目 | 当前值/做法 | 调整时看什么 |
| --- | --- | --- |
| 姿势间隔 | 1.25–2.9 秒，变化时少量随机幅度 | 是否有停留，而非匀速钟摆 |
| 头部弹簧 | 系数 7.5，阻尼比 0.74 | 先发起动作，有轻微回弹 |
| 俯仰弹簧 | 6.5 / 0.8 | 探头、抬落可见但不拉坏脸 |
| 身体弹簧 | 3.8 / 0.84 | 慢于头部，避免整张贴图同相旋转 |
| 发梢弹簧 | 3.1 / 0.65 | 跟随头身运动，延迟停稳 |
| 积分步长 | 分步不超过 12 ms，单帧 dt 封顶 100 ms | 帧率波动时不突然炸开 |
| 绑定最大范围 | 头部 Z 20°、身体 Z 8°、俯仰 54 源图 px、发梢 12 px | 这是关键形态最大值，不是每帧实际幅度 |
| 左右转头 X | 保持 0，未绑定网格 | 不把侧倾描述成真实侧脸转头 |

这些弹簧系数是脚本中的数值，不应标为 Hz。不同角色身材、取景和绑定范围需要重新调；不要把这组值当成通用配方。

动作优先级也影响观感：显式点头时平滑压低待机俯仰，防止两者抵消；单眼眨眼保留另一只眼睛；手势结束回到持续待机，不要求所有姿势参数归零。停止语音清除说话口型和手势，待机仍继续。

自然、开心、疑惑、惊讶、认真可手动选择。真实对话当前自动接入的是 `idle/listening/thinking/speaking` 状态，没有根据回复语义识别情绪。发梢仍是有限网格摆动，没有完整独立发束物理。

## 验收：先看连续画面，再看数字

1. 用真正的 `/stage` 取景录制约 20–30 秒，在正常直播尺寸播放。观察左右倾斜、上下起伏、不等长停顿、头身先后和回弹，不仅查看单张特写。
2. 并排看改前、改后的实际录像。不能通过放大整个播放器或更换裁切制造“幅度变大”。参考 Neuro 时同样排除剪辑缩放。
3. 查看极端姿态和表情组合：额头/眉眼接缝、眼睛漂移、嘴部补片、脖子断层、发边残色、画面裁切。惊讶眼睛仍应能闭眼。
4. 再检查实际变形后顶点、WebGL 状态和参数。最新版记录的脸部顶点中心跨度约 X=0.2075、Y=0.0981 模型单位，仅是变化存在的证据；不能直接折算为用户屏幕像素，也不是“自然”的评分。
5. 最后走真实音频链路：播放时张嘴，停止后闭嘴；观察端只显示公开的已播内容，私聊不外送，重连可恢复。演示页合成口型不算真实语音通过。

已有证据：`artifacts/changzheng-idle-bold.webm`、`idle-new-contact.png`、`changzheng-idle-check.json`、`changzheng-expression-check.json`。截至记录时，4 项待机检查和 21 项表情/生产状态检查通过；这是历史结果，修改后应重跑相关检查。真实 LLM/SAPI/观察端的 13 项通过发生在此前接线版本，不能冒充最新原生直播软件验收。

排错经验：

- 默认无头 Chromium 曾丢失 WebGL 上下文。独立测试浏览器使用 `--use-angle=swiftshader --enable-unsafe-swiftshader` 可稳定取证，但不代表桌面 GPU 性能或直播软件兼容性。
- `data-ready` 只说明加载流程走过。还要看实际截图、上下文状态和连续帧。
- 单眼眨眼用条件等待捕获闭眼窗口；固定等 180 ms 在软件渲染负载下容易错过，不要误判为功能坏了。
- 正常音量用约 45 ms 平滑，停止/零值在下一渲染帧直接闭嘴；超过 250 ms 未收到口型更新则闭嘴。不要把停止也做成缓慢衰减。

## 下次最短复用流程

在项目根目录使用已具备依赖的 Python。构建需要 Pillow、numpy 和低层 writer；浏览器检查需要 Playwright 与 Chromium；预览需项目 `.venv` 中的应用依赖。

```powershell
python probes/build_expression_rig.py
```

构建输出先在 `artifacts/runtime-expression-rig/bundle` 检查。部署时备份活动模型，将输出中的同名文件更新到 `web/models/changzheng`；动作脚本变更还需保留 `web/avatar-performance.js` 与播放器接线。不要只更新候选目录 `changzheng-expression`，实际页面读的是 `changzheng`。

先检查 17870 是否已有实例；没有时才启动独立预览，不要重复占端口或停掉用户现有服务：

```powershell
.\.venv\Scripts\python.exe probes/live2d_preview.py --port 17870 --avatar changzheng
```

刷新页面后访问 `http://127.0.0.1:17870/stage`。端口只是启动约定，不表示服务永久在线。17871 的历史参考页需要另行启动 `probes/reference_rig.py`，不能因为文档有 URL 就声称可访问。

```powershell
python probes/idle_motion.py
python probes/expression_performance.py
```

前者依赖 17870 预览。仅在修改语音/状态接线或需要复核真实链路时，再运行会发出真实模型请求的检查：

```powershell
$env:CHANGZHENG_TEST_MODEL = 'changzheng'
$env:CHANGZHENG_TEST_PREFIX = 'changzheng-expression'
$env:CHANGZHENG_TEST_SOFTWARE_RENDERING = '1'
python probes/live2d.py
```

迁移前一起保留源 PNG、构建脚本、低层 writer 版本、当前模型和网页驱动；清点被忽略或未跟踪的文件。需要 VTube Studio/直播姬原生播放同款动作时，另做 motion/参数驱动适配，并在目标软件中实际导入和播放。目前只验证了网页渲染，未完成原生导入和对外开播。

## 参考材料边界

2000 参考目录：`G:\SteamLibrary\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\2000_vts`。只读比较结构和渲染，不复制其纹理、关键形态或把运行时目录当成可换皮工程。目录名 `.8192` 中贴图实际为 4096×4096，应读实际尺寸。

Neuro 视觉参考：[官方账号片段](https://www.bilibili.com/video/BV1a99cYPEWA/)。本地参考视频只用于分析，没有加入交付素材。房间背景来源和许可记录在 `web/assets/rooms/NOTICE.md`，与角色模型版权分开管理。
