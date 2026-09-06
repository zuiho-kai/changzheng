# 长征酱：正面表情与动作版

2026-09-05。用户明确将重点从左右转头改为参考 2000 的表情、动作。当前方向是保持正面，用眉眼、嘴角和轻微身体动作表达状态；不继续投入侧脸投影或转头九宫格。

## 已落地

- 保留既有清晰半身立绘，11 个网格、17 个参数、2048×2048 贴图。
- 自然、开心（闭眼笑）、疑惑、惊讶（独立眼睛素材）、认真五种表现。
- 眉毛高低/倾斜、笑眼、开闭眼、嘴角形状、口型分别控制；惊讶眼睛仍能眨眼。
- 呼吸、轻晃、点头、单眼眨眼、短暂歪头。ParamAngleX 没有绑定任何网格，运行时也固定为 0。
- 待机重做为可读的姿势变化：六组侧倾/探头姿势，每 1.25–2.9 秒换姿势，头部先到、身体随后、发梢最后停稳，弹簧阻尼保留轻微回弹。点头时背景起伏平滑减弱，避免抵消动作。网格最大头部歪斜从 6° 提高到 20°、腰部倾斜从 3.5° 提高到 8°，俯仰位移从 22 提高到 54 源图像素；实际使用范围由待机姿势限制。保留少量呼吸，取消作为主动作的连续正弦摆动。
- `web/avatar-performance.js` 同时用于演示与实际 Live2D 页面。实际页面接收父页面的待机、倾听、思考、说话状态，重载后同步当前状态。
- 实际桌宠口型只由音频驱动；演示页的“说话口型”是明确标注的无声合成示例。停止时立即清除口型目标与动作，表情平滑回到自然。
- 四个命名表情可在演示页手动触发；真实对话自动使用四种状态表现。尚未实现根据回复语义自动选择“惊讶/开心”等情绪，不能把状态表现描述成语义情绪识别。

演示入口：<http://127.0.0.1:17871/>。原转头对照入口已替换成表情与动作页。桌宠：<http://127.0.0.1:17870/>，已有页面刷新后载入新模型。

## 验证

`python probes/expression_performance.py` 验证五种表情实际截图、点头和歪头结束回到待机、独立单眼眨眼、四种生产状态、停止和过期音频闭嘴。连续实录在 `artifacts/changzheng-expression-demo.webm`，当前机器结果见 `artifacts/changzheng-expression-check.json`。

`python probes/idle_motion.py` 录制实际房间页面，并采样 MOC3 变形后的嘴部网格中心，确认脸部横向和纵向确实移动、待机嘴巴闭合、左右转头仍为零。实录 `artifacts/changzheng-idle-room.webm`，结果 `artifacts/changzheng-idle-check.json`。这是本项目实现的待机运动，不声称复现 Neuro-sama 的内部算法。

视觉参考：官方账号 2025-02-27 切片 https://www.bilibili.com/video/BV1a99cYPEWA/ ，以及早期绿幕动作片段 https://www.bilibili.com/video/BV1s24y137aR/ 。参考视频只作本地分析，不加入发布素材。检查连续姿势和头身相对运动时，注意官方短视频自身有镜头缩放，不能把剪辑位移当成模型动作。验收以正常直播尺寸下连续录像的侧倾、探头、停顿、跟随和面部完整性为主；参数测试只用于辅助排错。前后实录对照 `/static/motion-review.html`，新版去掉开头加载段的录像 `artifacts/changzheng-idle-bold.webm`。

`CHANGZHENG_TEST_MODEL=changzheng`、`CHANGZHENG_TEST_PREFIX=changzheng-expression`、`CHANGZHENG_TEST_SOFTWARE_RENDERING=1` 下运行 `python probes/live2d.py`：13 项真实 LLM/本地 SAPI/观察端检查全部通过，本次停止到观察端闭嘴 171 ms。包括私密语音不外送、观察端重连恢复、未播内容清除、下一轮上下文等。两次探针都在独立 Chromium 中运行，使用 ANGLE SwiftShader 避免此前默认无头 GPU 上下文丢失；此结果不是桌面 GPU 性能测量。

机器记录：`artifacts/changzheng-expression-check.json`、`artifacts/changzheng-expression-live2d-probe.json`。

## 构建与素材

运行 `python probes/build_expression_rig.py`，输出 `artifacts/runtime-expression-rig/bundle`。活动模型为 `web/models/changzheng`；候选副本 `web/models/changzheng-expression`。该脚本继承低层 MOC3 writer，未使用参考模型的纹理或关键形态顶点。参考模型通过本机只读服务直接读取。

原图、脸底、闭眼/嘴型、惊讶素材分别在 `artifacts/changzheng-manual-assets/{source,blank,expression,surprised}.png`。原三个素材的提示词见 `MANUAL-RIG.md`。

新增惊讶素材使用内置 imagegen 编辑，生成结果为 1254×1254，完整结果保存到项目的 `surprised.png`，仅机械提取眼睛区域进入图集。其余表情通过既有局部网格关键形态制作。提示词原文：

> Precise facial expression edit for a Live2D sprite. Edit this exact 1254x1254 full image. Keep the entire composition, head position, frontal face angle, hair, face contour, nose, skin colors, star, neck and clothes IDENTICAL to the source. Change ONLY the interior of both eyes and their outlines into a clearly readable cute anime astonished expression: round wide white eyes with very small red-orange irises and tiny pupils, crisp expressive curved upper lashes. The eyes stay centered at their original coordinates (viewer left eye center x580 y336, right x723 y336). Each eye must remain inside its original small region: left x532..619 y302..373, right x680..776 y302..373. Keep all hair overlapping the eyes intact. Eyebrows slightly lifted, mouth stays closed and exactly as original. The result should feel surprised and comical yet pretty, matching the existing fine anime linework, NOT horror, NOT angry. Do not rotate, tilt, zoom or reposition anything. Keep magenta background unchanged, exact same framing and 1254x1254 size. No labels, no text, no extra symbols. This file is an aligned expression layer source for mechanical extraction of the eyes.

本次没有进行 VTube Studio 原生导入验收，也不含 `.cmo3` 工程。发丝仍使用有限的网格摆动，不是完整独立发束物理。
