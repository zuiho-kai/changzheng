# Sources

- PuppetLoom：`https://github.com/CheshireMew/PuppetLoom`，锁定 `f26c83dd31a48c644eb962971b9e21b9fa06f3f4`。上游 package.json 标注 `AGPL-3.0-or-later`。本包通过独立 checkout 的 CLI 和 Web SDK 适配；生成预览复制其 LICENSE。
- Anime2.5DRig：`https://github.com/852wa/Anime2.5DRig`，锁定 `7450341934a8ff77bf05b90d9f708786e3eb3996`。MIT，Copyright (c) 2026 hakoniwa。绑定与补件使用原始 rigger/genericparts；预览保持原始 app 的渲染算法，仅注入 agent 桥。生成产物保存来源许可。
- image2live2d：`https://github.com/Wzhang3912/image2live2d`，锁定 `b3fea7536f2d680897dbf5cce5a13046da75803c`。Apache-2.0。仅作为长征已使用的低层 MOC3 writer，通过显式配置路径加载，不在包内复制该项目源码。
- 长征：`probes/build_expression_rig.py` 与 2026-09-10 模拟器修复后 `avatar-performance.js`、`secondary-motion.js`。源码文件哈希见包内 `changzheng-provenance.json`。`changzheng.py` 只将原来的全局目录替换为 CLI 输入、输出和依赖路径；它保留小征原模板的坐标限制。
- `secondary-motion.js` 内的 spring 来自 Anime2.5DRig；随源码保留 `ANIME25D-LICENSE.txt`。

本包不附带用户角色原画、测试 PSD、上游示例素材或 Cubism Core。测试使用现有本地素材；这些素材的实际使用范围与软件源码分开记录。导出包的上游许可、运行时依赖和素材来源应随产物保留。
