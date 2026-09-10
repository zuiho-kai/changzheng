# cz-img2live2d

本子项目面向外部 agent。先读 README 的能力表及 `skills/cz-img2live2d/SKILL.md`。聚合长征、PuppetLoom、Anime2.5DRig 的原生能力；优先补适配，不另造绑定引擎。

- `src/cz_img2live2d/cli.py`：统一项目与原生 CLI。
- `anime.cjs` / `tune.cjs`：调用已锁定上游的 PSD、补件与设置实现。
- `review.py` / 预览模板：真实浏览器渲染、文件快照和 PCM 排练。
- `changzheng.py`：小征专用基准模板；不能把固定坐标换成比例缩放后宣布通用。

先跑 `doctor`。外部引擎使用显式配置，版本见 `engines.json`。CLI stdout 为 JSON；所有路径参数相对于调用者当前目录。一个角色的写操作顺序执行，保留各次构建与原生修订。

长征内开发只暂存到 `simulator/workspace/cz-img2live2d/`，走 17874 模拟器。不得用 17870、直播接收器、正在运行的直播窗口或发布目录 `web/` 做验收。

验证相关变更：`python -m pytest packages/cz-img2live2d/tests -q`。后端/渲染变更另跑实际 PSD 或小征素材的 build/bridge/review，不用这 6 项 CLI 回归替代视觉检查。`ACCEPTANCE.md` 记录已实测与未实测范围。

依赖来源、许可证与抽取文件哈希随包保留。不要将本地测试 PSD、用户图片、凭据或上游 Cubism Core 加进发布包。
