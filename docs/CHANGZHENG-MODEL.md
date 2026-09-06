# 长征酱 Live2D 初版交付

日期：2026-09-05。

## V2 优化

当前预览已更新为 V2，已打开的页面需刷新。下载 `artifacts/changzheng-live2d-v2.zip`；V1 ZIP 保留。

- 修正裙子在上衣后的错误遮挡顺序，遮住拆层补出的肤色腰带；未重绘角色。
- 待机周期改为 12 秒，小幅转头、呼吸和不等间隔眨眼。
- 播放器对正值嘴型采用 45 ms 时间常数平滑，明确停止和超时归零不经过缓动。
- 名字与角色区保持 10 px 间距，修复原来的 8 px 重叠。

`probes/refine_changzheng.py` 可复现本地重导出。V2 模型嘴型/闭眼/转头独立渲染通过；13 项真实语音和直播观察端回归通过，本次自动点击停止到观察端闭嘴测得 281 ms（与 V1 187 ms 属于不同单次采样，不作为性能提升结论）。嘴型阶跃在约 60 ms / 160 ms 分别到达 0.777 / 0.976，停止归零检查通过。证据保存在 `artifacts/changzheng-v2-*-check.json` 和 `artifacts/changzheng-v2-live2d-probe.json`。

下文保留 V1 制作记录。

- 实际本地预览：http://127.0.0.1:17870/
- 直播画面预览：http://127.0.0.1:17870/stage
- 模型：`web/models/changzheng/model.model3.json`
- 模型包：`artifacts/changzheng-live2d-v1.zip`
- 分层源稿：`artifacts/changzheng-layered.psd`
- 立绘：`artifacts/changzheng-standing.png`

参考图：[Steam 创意工坊「长征酱肖像替换」](https://steamcommunity.com/workshop/filedetails/?id=3750922022)，画师账号由页面标注为「大白兔喝柠檬水」。使用其中银白长发、金星发饰、红色水手领形象作为角色参考，再生成正面全身立绘。并非声称获得画师的现成 Live2D 或商用授权。

内置 imagegen 生成立绘。输出实际上是 RGB 棋盘背景，随后 See-through 提取出了真正透明的图层。官方 Hugging Face 演示第一次任务成功，后续诊断请求因剩余额度不足而失败；成功结果已下载，之后全部绑定、导出和运行发生在本机。

拆层设置：768、seed 42、左右拆分；23 个 PSD 图层。自动绑定采用 image2live2d 的原生 MOC3 导出工具，版本 b3fea7536f2d680897dbf5cce5a13046da75803c。最终 MOC3 为 8,078,912 字节，32 个绘制部件、38 个参数。

验收结果：`artifacts/changzheng-model-check.json` 的嘴型、眨眼、转头独立渲染检查通过；`artifacts/changzheng-live2d-probe.json` 的 13 项真实语音/直播观察端/打断检查全部通过，停止到闭嘴 187 ms；86 个自动测试与 8 个 subtests 通过。

限制：768 拆层的脸部细节低于源立绘；腰部衣服重建有偏差，头发有少量毛边；转头适合小幅动作。没有人工精修，也没有生成 Cubism 编辑器工程 `.cmo3`。尚未在 VTube Studio 或 B 站实际开播验收。

## 可复现本地导出

上游源码位于 `.reference/image2live2d-research`（不入库）。成功拆层的原始结果位于 `artifacts/runtime-changzheng-model/character.psd`，适配后的 PNG 图层位于同目录 `layers`。

```powershell
$env:PYTHONPATH='E:\a7\changzheng\.reference\image2live2d-research\src'
python .reference/image2live2d-research/tools/emit_cubism_bundle.py artifacts/runtime-changzheng-model/layers artifacts/runtime-changzheng-model/bundle
python probes/character_model.py
$env:CHANGZHENG_TEST_MODEL='changzheng'
python probes/live2d.py
```

## 实际使用的生成提示词

Use case: identity-preserve. Create a clean high-quality anime character full-body standing illustration for Live2D rigging, based closely on the two portraits of the SAME fictional character Long March / Loji / 长征酱 in the provided reference. Preserve her recognizable silver-white long hair, soft layered side bangs, single large GOLD five-point star hair clip on viewer LEFT, red-orange eyes, cheerful intelligent gentle face, white and gray sailor blouse with dark red sailor collar and red neckerchief. Extend naturally into a dark red pleated skirt, opaque dark thigh high stockings, simple dark loafers. Straight-on orthographic neutral standing pose, head upright centered, both eyes fully open, tiny CLOSED smiling mouth, arms relaxed slightly separated from torso and hands visible, feet separate, symmetric easy-to-rig silhouette. Hair reaches waist behind shoulders. Professional fine anime cel shading, beautiful polished line art, normal anime proportions not chibi. Full figure entire hair and shoes visible with clear margins. Plain genuine transparent background, no scenery, no game UI, no border, no lettering, no watermarks, no scanlines, no extra stars or floating particles. The image is a source illustration, not a picture of a Live2D editor. Portrait composition 1024x1536.
