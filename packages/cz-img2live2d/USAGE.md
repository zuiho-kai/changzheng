# cz-img2live2d 使用指南

项目背景和推荐分工见 [README](README.md)。以下是安装和 agent 操作参考。

给外部 agent 使用的图片转 Live2D 工具链，聚合长征、PuppetLoom 和 Anime2.5DRig。没有内部聊天机器人，操作入口是 CLI、JSON 和文件。单图的理解、分层、补图和视觉判断由调用方 agent 完成。

## 已接入的三方能力

| 来源 | 已接入 | 产物与边界 |
| --- | --- | --- |
| 长征 | 已有对齐素材的正面表情绑定、MOC3 编码；提取的状态/表情/视线/身体/发梢驱动；已有语音的 PCM 口型和停止排练 | `model.moc3`、贴图、表情/动作、源素材、独立 JS 驱动。当前是明确命名的小征模板，尺寸和坐标不适用于任意角色 |
| PuppetLoom | 原生 PSD 导入、自动绑定、网格/权重/关键形/修订等完整 CLI 透传、素材接入、原生姿态图、Web SDK 预览、原生项目导出 | 可继续精调的原生项目。Cubism 导出命令已可转发，但必须单独安装上游 exporter；本轮未实测该出口、真实设备或 Spout2 |
| Anime2.5DRig | 原生 PSD 解析、部件/锚点/发束识别、缺失闭眼/闭嘴补件、原生浏览器自动绑定和物理、参数/图层设置 | PSD、原图坐标图层、绑定报告、设置 JSON、浏览器运行时；本后端不导出 MOC3 |
| 聚合层 | 同一角色项目保存各后端结果；Anime 的补件与原画图层进入 PuppetLoom；统一错误、来源、预览、录像及导出 | 中转保留绘画图层与位置，不宣称网格/关键形/物理可以跨引擎无损互换 |

## 安装

```powershell
python -m pip install -e './packages/cz-img2live2d[review]'
python -m playwright install chromium
```

只有构建时无需 Playwright。Node 24+ 用于两个上游 JS 引擎。已有 Python 环境没有 pip 时，可使用 `uv pip install --python <python.exe> -e './packages/cz-img2live2d[review]'`。

先按 `src/cz_img2live2d/engines.json` 中的 URL 和精确 commit 准备独立上游 checkout。示例：

```powershell
git clone https://github.com/CheshireMew/PuppetLoom deps/PuppetLoom
git -C deps/PuppetLoom checkout --detach f26c83dd31a48c644eb962971b9e21b9fa06f3f4
git clone https://github.com/852wa/Anime2.5DRig deps/Anime2.5DRig
git -C deps/Anime2.5DRig checkout --detach 7450341934a8ff77bf05b90d9f708786e3eb3996
git clone https://github.com/Wzhang3912/image2live2d deps/image2live2d
git -C deps/image2live2d checkout --detach b3fea7536f2d680897dbf5cce5a13046da75803c

# 在 deps/PuppetLoom 中构建 CLI 与浏览器 SDK，不启动桌面应用：
Push-Location deps/PuppetLoom
npm ci --ignore-scripts --no-audit --no-fund
node scripts/build-cli.mjs
npm run build -w @puppetloom/web-runtime
Pop-Location
```

配置是机器本地文件；不从长征目录偷偷寻找依赖。示例在项目根运行：

```powershell
cz-img2live2d --config local-engines.json configure --puppetloom deps/PuppetLoom --anime25d deps/Anime2.5DRig --moc3 deps/image2live2d
$env:CZ_IMG2LIVE2D_CONFIG = (Resolve-Path local-engines.json).Path
cz-img2live2d doctor
```

Cubism 网页排练还需要拥有使用权限的 runtime 文件。长征环境可配置 `configure --cubism-vendor simulator/workspace/vendor`；包内不附送 Cubism Core。依赖构建脚本和 exporter 的更多选项以已锁定上游源码为准。

## 从图片开始

```powershell
cz-img2live2d init --image character.png --project work/character
```

返回 `needs_assets` 后，agent 根据原图准备同画布、保留原画坐标的分层 PSD。可调用自己的分层或图片编辑工具；至少检查脸底、前后发、眉眼、眼白/虹膜、开闭嘴、颈部及衣服等实际存在的部件。不要求每个角色有同样图层，不伪造缺少的肢体。

```powershell
cz-img2live2d assets --project work/character --psd character-layered.psd
cz-img2live2d build --project work/character --backend anime25d
cz-img2live2d bridge --project work/character
```

`bridge` 使用 Anime 原生补件和对齐图层创建一个新的 PuppetLoom 项目，并通过 PuppetLoom 的 `enhance` API 接入原始张嘴素材。已有 PuppetLoom 构建保留。通用闭眼/闭嘴补件会明确标记 `synthetic`，需要 agent 判断是否符合该角色；原生图层没有被补件替换。

已经有完整 PSD 时，可直接 `init --psd ...`，再 `build --backend puppetloom`。`inspect` 返回当前各后端构建、源文件和来源；`inspect --backend puppetloom` 调用原生 PSD 预检。

## 精调与全部原生能力

不用重新实现 PuppetLoom 的命令体系：

```powershell
cz-img2live2d native -- capabilities --json
cz-img2live2d native --project work/character -- describe
cz-img2live2d native --project work/character -- agent specification --scope eyes
cz-img2live2d native --project work/character -- agent plan --spec eyes.json
cz-img2live2d native --project work/character -- agent apply --spec eyes.json
cz-img2live2d native --project work/character -- history
cz-img2live2d native --project work/character -- actions plan
```

`--` 后所有参数原样传递，`--project` 自动指向该角色最新的 PuppetLoom 原生项目。网格、权重、形变、动作、物理、导出及控制接口的具体参数，读取配置根目录下 `docs/AGENT_USAGE.md`，使用 `native -- <command> --help` 查当前接口。原生协议的 `baseRevision`、失败与接受状态保留，不通过直接修改 `puppetloom.json` 绕开它们。

Anime 的预览桥 `window.cz` 提供 `settings()`、`applySettings(value)`、`setState(state)`、`mouth(value)`、`stats()`。`review` 将原生设置快照保存为 `reviews/<id>/settings.json`；agent 可以在独立预览上试调，不用手动拖控件。需要持久化时使用下述 tune 命令。

```powershell
cz-img2live2d tune --project work/character --settings adjusted-settings.json
```

使用上游原生设置验证器及实际滑条范围检查 PSD 指纹、图层 ID 和数值，成功后创建新构建，不覆盖旧版本。设置不会转换成 PuppetLoom 的物理参数；bridge 只中转绘画图层。

## 真实渲染与排练

长征中先启动 `启动模拟器.ps1`，打开 `http://127.0.0.1:17874/sim`。所有候选网页与模型只写入 `simulator/workspace/cz-img2live2d/<id>/`，不会替换已有排练模型。

```powershell
cz-img2live2d review --project work/character --backend anime25d --workspace simulator/workspace --audio existing.wav
cz-img2live2d review --project work/character --backend puppetloom --workspace simulator/workspace --audio existing.wav
cz-img2live2d review --project work/character --backend puppetloom --native-sheet
```

默认 30 秒：待机、注意/倾听、思考、语音口型、打断。报告包含已实际渲染文件的哈希清单、截图和连续 WebM。录音解码成真实 PCM 驱动口型；录制视频本身静音，不构成人耳音质验收。参数变化只证明控制链路，需要看实际嘴部和原生能力报告确认动画效果。缺陷和通用性未验收时不写“完成制作”。

独立使用时，将一个含 `index.html` 的静态目录作为 `--workspace`，启动自己的 localhost 静态服务，并通过 `--base-url` 指定目录 URL。长征内部开发坚持使用 17874，禁止接触 17870、直播窗口、真实弹幕与 `web/` 发布目录。

## 小征 MOC3 基准路径

```powershell
cz-img2live2d init --image source.png --project work/changzheng
cz-img2live2d assets --project work/changzheng --changzheng aligned-assets
cz-img2live2d build --project work/changzheng --backend changzheng
cz-img2live2d review --project work/changzheng --backend changzheng --workspace simulator/workspace --audio existing.wav
cz-img2live2d export --project work/changzheng --backend changzheng --output out/changzheng
```

`aligned-assets` 必须是同一套 1254×1254 的 `source/blank/expression/surprised.png`。这条路径保留当前长征能力，不声称已经泛化到任意角色。其他角色的全流程由 PSD/补图和两个原生绑定引擎承担。

## 导出与文件契约

```powershell
cz-img2live2d export --project work/character --backend puppetloom --output out/character
# 单独配置上游 Cubism exporter 后才使用：
cz-img2live2d export --project work/character --backend puppetloom --format cubism --output out/character-cubism
```

导出必须使用新目录。`model/` 是原生模型，`source/` 保留输入，`project.json` 保留重建入口；长征另有 `runtime/`。每个 build 使用新的目录，失败不会切换到半成品。不同后端可以在同一角色下并存；不要并发修改同一个角色项目。

CLI stdout 是 JSON，原生退出码与错误内容保留在响应中。成功为 0；输入/文件错误为 2；引擎失败为 3。`needs_assets` 和 `awaiting_visual_review` 不等于制作成功。引擎自身返回的制作状态始终位于 `native`，不要忽略。

依赖与抽取源码记录见 [THIRD_PARTY.md](THIRD_PARTY.md)。Agent 使用入口见 [SKILL.md](skills/cz-img2live2d/SKILL.md)。本轮实测记录见 [ACCEPTANCE.md](ACCEPTANCE.md)。
