# 首版验收记录

日期：2026-09-10 至 2026-09-11（香港时间）。当前结论：三方适配、图层中转、原生编辑入口与导出已经可运行。角色质量与接口连通分开记录。

## 实际执行

| 项目 | 实测结果 |
| --- | --- |
| 安装包 | 构建 Python wheel，在全新虚拟环境安装，切换到项目外层目录运行；没有使用 editable 源码包 |
| 小征模板 | 4 张已有对齐素材 → 11 网格、20 参数、2048 图集、7,229,504 字节 MOC3；浏览器加载并连续排练 |
| 重建 | 从导出项目的源文件在全新环境重建，MOC3 SHA-256 与原构建一致：`83d30450199485d9cab547e71ae666da8d1ca3c06c480f2abda5841079aa5ce8` |
| PSD A | Anime 原生绑定后 17 个图层；包含原生通用闭眼/闭嘴补件。中转后 PuppetLoom 19 张纹理，原生 enhance 接受张嘴素材，verify 通过 |
| PSD B | Anime 原生绑定后 20 个图层，已有闭眼/闭嘴，无新增通用补件。中转后 PuppetLoom 22 张纹理，enhance 接受张嘴素材，verify 通过 |
| 设置 | 修改 Anime 原生 `physAmp` 后经原生校验器保存新构建，重新渲染验证设置载入流程 |
| 原生制作 | capabilities 返回当前构建；通过统一 CLI 调用 actions plan/apply，在 PSD B 的 PuppetLoom 项目创建 revision 1；history 返回该修订与证据目录 |
| 导出 | 小征 MOC3 包和 PuppetLoom 原生可移植包实际导出；后者原生验证通过 |
| CLI 回归 | 6 项通过：单图缺素材、独立目录调用、拒绝覆盖、失败保留当前项目、原生错误传播、拒绝将 Anime 导出冒称 Cubism |

测试 PSD 是两个已有上游样例，源码包不附带它们。PSD A SHA-256：`e17bb61c8dc1f2bc891695d306535d4674068648d2fabe87a1a2bc1b2ab460c7`；PSD B：`1e27ef2d5359143f40b6a48e91db1b7f227aa1e26dfbf6a892d9b685e485a42f`。

## 实际画面与证据

本机总入口：[排练录像](../../artifacts/runtime-cz-img2live2d/review.html)。本节的录像和报告保留在开发机，未上传仓库或安装包，因此这些本地证据链接在 GitHub 上不可访问。以下均在 17874 模拟器独立子目录实录，使用 Chromium SwiftShader；不是桌面 GPU 性能测试。

- 小征：[报告](../../artifacts/runtime-cz-img2live2d/changzheng/reviews/changzheng-7d443a0a33/report.json)。约 30 秒状态与 PCM 排练，参数响应/停止归零通过。序列抽帧可见张嘴、身体/头发跟随；没有在这些抽帧中看到此前那种脸突然放大。
- PSD A / Anime：[报告](../../artifacts/runtime-cz-img2live2d/sample-a/reviews/anime25d-0ddb669ffe/report.json)。已查看相同设置构建的连续序列和嘴型图，眨眼、开闭嘴及头发运动可见。最后一次复测增加了“等待设置加载完毕再 ready”的修正。
- PSD A / PuppetLoom：[报告](../../artifacts/runtime-cz-img2live2d/sample-a/reviews/puppetloom-b11cb52dd3/report.json)。原始直导时嘴一直张开；中转补件后实际静态闭嘴、张嘴截图均可见，连续序列也显示嘴型变化。当前原生 grouped 绑定仍关闭 gaze 和 bodyFollow。
- PSD B / PuppetLoom revision 1：[报告](../../artifacts/runtime-cz-img2live2d/sample-b/reviews/puppetloom-3be5f4b1d9/report.json)。已查看开闭嘴、连续抽帧；该素材支持 bodyFollow，gaze 仍关闭。动作库已创建，但并未把每个具名动作逐一触发后做视觉验收。

所有最终排练报告均无 page error，真实测试录音的口型参数响应和停止归零检查通过。视频是静音 WebM，包含加载阶段和额外开闭嘴姿态检查；30 秒指排练场景时长。连续抽帧只用于 agent 检查可见问题，不等同用户已经认可动作自然度。机器报告仍保持 `visualReview: unreviewed`，本文件记录本轮 agent 实际观察范围，不冒充用户接受。

## 仍未验证或实现的范围

- 没有在本轮调用外部图像模型，把一张全新平面原图全自动分层。单图项目生成素材请求，由外部 agent 完成分层/补图，再恢复 CLI 流程。
- 长征 MOC3 构建仍是专用模板；不承诺任意角色都能直接使用该模板。
- PuppetLoom Cubism exporter 尚未安装验证。本轮没有它导出的 `.cmo3/.moc3`，也没有 VTube Studio、摄像头、麦克风、Spout2 或线上 TTS 实测。
- 只中转图层和补件，未实现 Anime 参数、物理和精调结果到 PuppetLoom 的无损迁移。
- 当前两份 PuppetLoom 样例采用原生保守绑定。没有为了宣称功能齐全而修改其 disabled features。
- 上述制作验收未修改直播目录与 17870 服务。源码和安装包发布不代表已将模型部署到直播环境。
