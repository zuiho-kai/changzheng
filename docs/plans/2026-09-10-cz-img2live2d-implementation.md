# cz-img2live2d Implementation Plan

**Goal:** 交付可独立安装的三方聚合 CLI 和 agent Skill，并实际构建、渲染三方结果。

**Architecture:** Python 统一项目与 JSON 接口，PuppetLoom 原生 CLI 适配，Anime2.5DRig 原生 JS 自动绑定及播放器适配，长征既有正面表情构建与驱动提取。依赖显式配置并记录版本，各后端保留自己的编辑工程。

**Tech Stack:** Python、Node.js、Pillow、numpy、Playwright、三方原生代码。

1. 在 `packages/cz-img2live2d/` 创建包、依赖版本锁定表和独立配置命令；不修改现有排练调试文件。
2. 实现 init/inspect/build/native/export 命令。单图输入生成素材请求，PSD 输入可调用两家原生绑定，同一任务保留各后端结果。长征精确素材作为明确命名的基准模板。
3. 实现 Anime2.5DRig Node 桥与浏览器控制桥，保留原渲染和物理实现；原生设置 JSON 可持久化并用于下一次预览。
4. 实现模型预览暂存到模拟器独立子目录，录像和截图报告绑定具体输入及构建。PuppetLoom 使用其原生 render/record 接口。
5. 写 Skill、README 和来源声明；明确已适配能力、运行时差异、原生导出依赖。
6. 安装包，实跑小征 MOC3 和两家 PSD 构建，检查真实输出与渲染。针对后端失败传播、隔离输出和缺素材状态跑必要回归。

用户已要求 go，本轮连续执行，不再请求执行方式选择。仅提交本子项目与相关设计文件，现有工作区修改保留。
