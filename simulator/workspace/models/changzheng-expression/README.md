# 长征酱 · 正面表情与动作版

2026-09-05。入口 model.model3.json。在小征当前 Cubism Web 运行时已实际验证；未在 VTube Studio 或 Cubism 编辑器验收。

本版不使用自动拆层/绑定。半身原画、无五官脸底、眼口表情由内置 imagegen 准备，随后手工指定眼口网格、头颈蒙皮权重和关键姿势，再导出 MOC3。

- 原生贴图 2048×2048，素材 1254×1254。
- 11 个网格、17 个参数。眼口、笑眼、嘴角、眉毛高低与倾斜独立控制，惊讶使用独立眼睛素材。
- 正面表现，左右转头禁用；包含小幅呼吸、轻晃、点头、歪头和单眼眨眼，不包含 .cmo3 工程。
- 构建脚本：项目 probes/build_expression_rig.py；数值控制点：rig-source.json。命名表情位于 expressions/。
- 网页表演控制器为项目 web/avatar-performance.js，真实嘴型由音频驱动。完整制作与验证记录：docs/EXPRESSION-RIG.md。
- 二进制序列化复用 Apache-2.0 项目 https://github.com/Wzhang3912/image2live2d 的低层 writer，版本 b3fea7536f2d680897dbf5cce5a13046da75803c。未调用自动 rig、模板或 landmark。

参考：https://steamcommunity.com/workshop/filedetails/?id=3750922022 。页面标注画师 B 站账号「大白兔喝柠檬水」。立绘是基于角色参考生成的衍生素材，不是原画师提供的模型；角色与参考美术权利归各自权利人，不声明商用授权。
