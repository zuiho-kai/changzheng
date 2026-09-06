# 2000 模型对照：转头问题定位

后续用户明确将重点改为表情和动作，停止投入左右转头。当前成果见 [正面表情与动作版](EXPRESSION-RIG.md)。本文保留为此前问题的分析记录，不再是下一步任务清单。

2026-09-05。用户提供的实际目录为 `G:\SteamLibrary\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\2000_vts`。

结论：长征酱当前形变试作的转头尚未合格。主因是底图未拆开、不同部件没有独立的形态制作；此前统一位移和浅椭球投影都不能代替这一步。清晰度与语音停止检查通过不代表绑定质量通过。

## 本地实测

运行 `python probes/reference_rig.py --port 17871`，访问 <http://127.0.0.1:17871/>。两模型使用同一个 PIXI/WebGL 播放器，关闭自动更新、物理与动作，直接把 ParamAngleX/Y/Z 输入 Cubism Core。每次恢复其他参数默认值，排除物理与动作叠加。眼睛、嘴型滑杆按各模型自身范围解释，不把不同模型的口型最大值当作相同常数。

实测正面、左右极限、斜向转头、转头叠加闭眼/张嘴。2000 在关闭物理的情况下仍有完整侧向脸型和五官变化；长征酱虽然可以移动，侧脸关系不足。正常参考模型在本播放器内能正确显示，因此当前问题的主要原因是模型制作。

独立 Chromium 的默认硬件渲染在后续截图时偶发 WebGL context lost；最终证据采用 ANGLE SwiftShader，5 组姿态及完整左右摆动均检查上下文未丢失。页面也会显示上下文丢失状态。此处验证的是模型形态，不是用户桌面 GPU 性能。连续实录：`artifacts/reference-rig-yaw.webm`。

| 项目 | 2000 | 长征酱当前试作 |
| --- | ---: | ---: |
| ArtMesh | 203 | 9 |
| 参数 | 78 | 8 |
| Warp Deformer | 125 | 0 |
| Rotation Deformer | 9 | 0 |
| 贴图实际尺寸 | 4096×4096 | 2048×2048 |
| 物理组 | 26 | 0（当前 model3 未引用物理） |

目录名含 `.8192`，图片实际是 4096×4096；不能根据目录名判断清晰度。网格和变形器数量仅用来说明结构差异，不是必须追求的数量指标。直接编辑网格关键形态也能制作 Live2D；这里的问题是所有区域共用粗略形变，而非“只要有变形器就自然”。

## 从参考文件实际读到的结构

`.cdi3.json` 明确把 ParamAngleX 和 ParamAngleY 组合。MOC 中 `Rotation` 绑定 ParamAngleZ 的 -30/0/30 三个键；其子级 `Warp16`、`Warp19`、`Warp26` 等分别绑定 X/Y 的 -30/0/30，形成各自的 9 个关键形态。`Warp16` 下还有 `Warp9`、`Warp10` 等继续细分的 X/Y 变形器。不是把一个全身网格绕统一假想曲面扭曲。

VTube Studio 的配置把 FaceAngleX 映射到 ParamAngleX，输入输出范围均为 -30..30，Smoothing=15；Y 的输入 -20..20 映射到 -30..30，Smoothing=15；Z 的 Smoothing=30。物理的输入使用头部角度等，输出再驱动发束、裙子等。平滑和物理改善运动过程，侧脸轮廓本身已经写在模型中。

MOC 版本字节是 3，现有低层完整解析器仅支持版本字节 1，因此未用它重写或转换参考模型。只读公共前缀表，参数 ID、网格 ID、每个网格的顶点数量均与官方 Cubism Core 的实际加载结果逐项校验后，才记录结构。报告保存元数据，不复制参考纹理或关键形态顶点。

该目录包含运行时 `.moc3`、贴图和配置，没有 `.cmo3` 编辑工程或 PSD，因此不能直接把这个目录当成可编辑工程去替换画皮。

## 长征酱需要重做的具体部分

1. 将脸底/轮廓、鼻、眼白、虹膜、上下眼皮、眉、嘴、前发、左右侧发、后发、颈和衣领拆开，并补全遮挡区域。现有连续 `BodyHeadSkin` 不能独立改变脸颊、发际线和脖子的遮挡关系。
2. 以原画为依据，先制作正面、左右、上下及四角的关键形态。远侧眼宽、鼻口位移、下巴位置和发际线各自校正；不能给所有部件套同一个球面函数。
3. 用头部 Z 的父级旋转承载各部件的 X/Y 变形，眼口局部形变放在相应子级。先验收 X/Y 九宫格和眨眼、口型组合，再加发束物理。
4. 以当前同播放器参考页为外观验收基线。截图变化、二进制可加载和参数数量都不能单独充当“动作自然”的证据。

官方说明与实际结构一致：[变形器](https://docs.live2d.com/en/cubism-editor-manual/deformer/)、[X/Y 关键形态](https://docs.live2d.com/en/cubism-editor-manual/keyform-xydirection/)、[父子层级](https://docs.live2d.com/en/cubism-editor-manual/setting-of-parent-child-relation/)。官方同时说明：大幅旋转直接用网格坐标线性插值会经过收缩形态，应按用途使用旋转变形器。

证据：`artifacts/reference-rig-check.json`、`artifacts/reference-rig-center.png`、`artifacts/reference-rig-left.png`、`artifacts/reference-rig-right.png`、`artifacts/reference-rig-upper-left.png`、`artifacts/reference-rig-blink-turn.png`。
