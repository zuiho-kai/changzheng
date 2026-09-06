# 长征酱手工绑定

**2026-09-05 对照修正：本页记录的是网格形变试作，转头外观尚未验收通过。** 用户提供 2000 模型后，同播放器实测确认当前统一底图形变缺少必要的拆层及部件关键形态。详见 [参考模型分析](REFERENCE-RIG-2000.md)。以下语音与加载检查不能等同于专业 Live2D 绑定质量。

用户反馈 V2 清晰度与动作不自然，因此更换制作路线。

内置 imagegen 将原立绘准备成 1254×1254 半身素材，并生成位置一致的无五官脸底、闭眼与说话表情。保留银白发、金星、红色水手领和原画风格。原版拆层后面部约 86 px 宽，本版约 250 px 宽；这是素材细节预算，不等同于恢复原图不存在的细节。

自己编写 `probes/build_manual_rig.py`：手工定义 9 个网格、8 个参数。主网格是连续蒙皮，头部枢轴 (646,510)，颈部 y=440..585 平滑过渡，肩部与呼吸同步，外侧发尾单独加权。眼睛、闭眼线、眉毛、开闭口使用独立贴图区域和局部网格。没有运行自动 landmark、骨架或变形模板。

二进制封装仍复用 image2live2d MOC3 writer。不是在 Cubism 编辑器里操作，没有 `.cmo3` 工程。属于小幅半身绑定；主头发与身体尚未全面拆成独立补全图层，不能做大角度侧脸或独立发束物理。

原生贴图 2048×2048，不经低分辨率 PSD。修正 Cubism 多参数关键帧排列顺序与坐标方向，色键处理移除洋红背景和发丝残色。

## 验收

- 对照页：http://127.0.0.1:17870/static/rig-review.html
- 桌宠：http://127.0.0.1:17870/ （已打开的页面需刷新）
- 实际渲染：开闭嘴、闭眼、转头；自然状态、眼睛 0.4 / 嘴型 0.5 / 转头 18 的组合、动态演示截图均已查看。
- 13 项真实语音、直播观察端重连、停止清除未播放上下文检查通过；停止到观察端闭嘴单次 219 ms。
- 对照页使用同一 WebGL 上下文渲染两版，修正多上下文交替空白的问题。

证据：`artifacts/changzheng-manual-comparison.png`、`changzheng-manual-combined.png`、`changzheng-manual-motion.png`、`changzheng-manual-desktop-optimized.png`。机器验收：`artifacts/changzheng-manual-model-check.json`、`changzheng-manual-live2d-probe.json`。

## 重建

素材：`artifacts/changzheng-manual-assets`。运行 `python probes/build_manual_rig.py`，输出 `artifacts/runtime-manual-rig/bundle`。依赖 Pillow、numpy 和 `.reference/image2live2d-research/src` 下的低层 MOC3 序列化器。源码与控制点全部保留。

## 内置 imagegen 提示词

### 半身素材

Create a high resolution HALF-BODY Live2D source illustration of EXACTLY the same anime girl in the provided image, preserving the drawing style, face, red orange eyes, long silver white hair, gold star clip on viewer left, white sailor blouse red collar and neckerchief. Frame from top of hair to just below waist, facing straight forward, centered, neutral closed tiny smiling mouth, fully open symmetrical eyes. Arms relaxed and just slightly away from torso, whole shoulders and hair visible, hair continues down behind arms. The face should occupy at least 420 pixels width in a 1536x1536 square image. Keep beautiful detailed original line art and fine cel shading, NO blur, NO soft painting, NO glossy 3D. This is a precise identity-preserving enlargement and half body reframing for manual mesh rigging, not a redesign. Solid pure flat MAGENTA #FF00FF background (no checkerboard, no transparency simulation, no texture, no glow or shadows on background). Single character only, no text, no watermarks, no frames. Make a square 1536x1536 image.

实际返回 1254×1254，面部约 250 px；没有将请求尺寸冒充实际尺寸。

### 脸底

Precise technical Live2D layer preparation edit. Keep this EXACT image, canvas size, pose, hair and every clothing pixel unchanged. REMOVE ONLY the two eyes including irises, whites, eyelash outlines, eyebrows, and the tiny mouth line, replacing ONLY those facial features with matching clean smooth pale skin, preserving the nose, face contour, skin lighting and all hair that overlaps the face. This is a blank face base layer for a puppet so no eyes and no mouth is intentional. Do not redraw or reposition the head or anything else. Retain exact magenta background. No new objects, no text. Exact same dimensions as input.

### 眼口表情

Technical Live2D expression edit on this exact 1254x1254 illustration. Preserve every position, head contour, hair, nose, clothes, colors and background exactly. Change ONLY both eyes to gently fully CLOSED eyelids with thin elegant downward curved dark eyelash lines, and change ONLY the mouth to a small naturally OPEN speaking mouth (width approximately 42 pixels and height 26 pixels centered at the same original mouth center), with a dark warm interior, tiny light upper teeth and subtle pink tongue. Neutral friendly speaking expression, NOT a big laugh, NOT exaggerated. The closed eye curves should lie near the original lower eyelid line. Do not move eyebrows, head, neck or body, do not zoom. Exact same magenta background, exact same canvas. No text.
