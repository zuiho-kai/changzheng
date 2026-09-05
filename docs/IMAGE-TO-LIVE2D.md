# 图片转 Live2D 调研与小型实测

调研日期：2026-09-05。结论：优先验证 See-through 拆图，加 image2live2d 自动绑定，最后用现有 Cubism 渲染器验收。完整链路仍是实验方案；本次实际跑通的是分层测试素材到可驱动 MOC3。

## 需要分清的产物

1. 分层 PSD / RGBA：包含头发、脸、眼睛、嘴、身体及被遮住区域的补画，尚未完成绑定。
2. 可驱动模型：网格、参数关键形、遮罩、物理、贴图和模型文件。真正接入当前小征需要完整的 model3.json + moc3 包。
3. 神经网络动态头像 / 视频：可展示动作，但不自动等于可编辑的 Cubism 资产。

Cubism 官方支持从 PSD 导入 ArtMesh，随后自动生成网格；这些工具能减少编辑工作，但仍需要可用分层与参数制作。[PSD 导入](https://docs.live2d.com/en/cubism-editor-manual/psd-import/)、[自动网格](https://docs.live2d.com/en/cubism-editor-manual/mesh-edit/)。

## 候选路线

| 项目 | 实际作用与限制 | 对小征的判断 |
|---|---|---|
| [See-through](https://github.com/shitagaki-lab/see-through) | 动漫立绘拆成至多23类补全后的图层，输出PSD；不包办完整绑定。官方提供NF4、offload等低显存路径。 | 首选拆图候选。 |
| [Wzhang3912/image2live2d](https://github.com/Wzhang3912/image2live2d) | 从分层素材构建网格、参数和物理；主目标为nijilive，另有MOC3和实验性CMO3导出。默认CLI并不写MOC3，需要另走真实导出工具。 | 已验证导出及当前渲染器兼容性，正式立绘效果待验证。 |
| [autoLive2d](https://github.com/KonshinHaoshin/autoLive2d) | PSD到MOC3；借助本机Cubism 5.1 JAR/DLL与Java桥接，部分参数仍缺失。 | 可作备用实验，绑定依赖特定编辑器版本。项目名中的official指使用厂商组件，不表示项目获得官方支持。 |
| [Stretchy Studio](https://github.com/MangoLion/stretchystudio) | 接收See-through PSD，网格变形与自动绑定，支持Spine JSON导出。 | 适合快速制作类Live2D木偶；接小征需要另一套渲染适配。 |
| [Talking Head Anime 4](https://github.com/pkhungurn/talking-head-anime-4-demo) | 单图神经动态头像；快速学生模型需逐角色蒸馏，作者示例约30小时/A6000；模型权重为CC-BY-NC 4.0。 | 不选作未来商业直播的默认路线，也不是MOC3转换器。训练时间是作者报告，非本机测试。 |
| [Bunraku](https://github.com/SparcAI-Inc/Bunraku) | 论文目标为单图到可编辑动态角色；检查时公开仓库只有readme，没有可运行推理代码与权重。 | 观察项，暂不能直接部署。可看[项目演示](https://bunraku-live2d.github.io/)。 |
| [Qwen-Image-Layered](https://github.com/QwenLM/Qwen-Image-Layered/blob/main/README.md) | 通用图片转多层RGBA。 | 可比较拆图质量，但仍需把图层映射为角色部件并绑定；不能直接接到Cubism加载器。 |

搜索中还出现 Aiko Forge，但其公开 GitHub 页面及仓库 API 在本次检查返回404；没有用旧索引里的演示和成本宣传作落地依据。Bunraku 的完整效果与性能也未在本机复现。

## 本机适配

nvidia-smi 实测为 RTX 3070 Laptop GPU，8192 MiB 显存。See-through 文档给出的1280分辨率标准流程约需12–16GB；NF4路径约8GB峰值，也支持降低到1024并使用offload。因此本机值得尝试1024低显存配置，但8GB余量偏紧，不能保证当前桌面占用下不会OOM。[官方低显存说明](https://github.com/shitagaki-lab/see-through#low-vram-users)。

拆图和绑定应放在角色导入时离线完成；日常聊天/直播只驱动生成后的模型。这样图片模型的推理耗时不会叠到每条回复的TTFT上。这是结合本项目架构的工程建议。

## 本次实测结果

源码固定在 Wzhang3912/image2live2d 的 b3fea7536f2d680897dbf5cce5a13046da75803c，位于 .reference/image2live2d-research；没有安装大型AI权重，也没有上传用户图片。

- 默认CLI完成分层样例绑定，报告30个部件、40个参数，确实未输出MOC3。
- 调用项目 tools/emit_cubism_bundle.py 后，生成8,746,944字节MOC3以及贴图/JSON文件。
- 用小征现有的Pixi 6、pixi-live2d-display 0.4和Cubism Core实际加载成功。
- 停止自动动画后，把ParamMouthOpenY从0改到1，分别截图，画面发生变化；已人工查看截图确认嘴巴开合。
- 这是上游生成的简单几何测试角色，输入已经分层；尚未验证任意单张立绘的拆图、遮挡补全、自然转头和成品美术质量。

证据：artifacts/image2live2d-research.json、image2live2d-sample-closed.png、image2live2d-sample-open.png。加载验收脚本：probes/image2live2d_research.py。

复现顺序：设置PYTHONPATH指向上游src，运行其CLI的--sample和--fullbody生成测试分层，再调用tools/emit_cubism_bundle.py，最后执行本项目probes/image2live2d_research.py。测试产物位于artifacts/runtime-image2live2d，未接入日常角色设置。

## 下一步取舍

建议取一张有使用权的正面动漫立绘：单人、眼口清晰、手不遮脸、头发与服装轮廓清楚。先做以下小实验，再决定是否把自动转换做成产品功能：

1. See-through 1024 NF4拆图，记录实际显存、耗时和分层PSD。
2. 检查眼白/瞳孔/眼皮、口腔、前后发、脸和脖子的遮挡补全；必要时修少量图层。
3. 用已验证的真实MOC3导出路径生成模型。
4. 在小征里验证闭眼、开口、轻微转头、头发摆动和组合参数；必须检查动作中的接缝与穿帮。
5. 连续播放语音并反复Stop，确认渲染耗时不拖慢声音和输入。

第一版目标是身份稳定、眨眼说话自然、可随时打断。大幅侧脸、复杂手势、饰品与衣物的大动作留给人工精修。不要把其他角色的贴图简单替换当作通用绑定：不同脸型、五官位置和遮挡关系会使原参数不再适用。
