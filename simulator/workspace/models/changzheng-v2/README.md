# 长征酱 · 自动建模 V2

本地实验模型，2026-09-05。运行入口：`model.model3.json`。
包含真正的 Cubism 3 MOC3、透明纹理、物理配置与动作；不是 GIF 或视频。

参考来源：[长征酱肖像替换](https://steamcommunity.com/workshop/filedetails/?id=3750922022)。
页面标注画师 B 站账号为「大白兔喝柠檬水」。参考的是银白长发、金色星形发饰、红色水手领版本。
本模型的正面立绘由内置 imagegen 基于该游戏肖像重新生成，并非原画师提供的模型。
原角色和参考美术权利仍归各自权利人；这里不声明获得商用或重新分发授权。

制作：imagegen 正面立绘 → 官方 See-through 在线演示 768 分辨率、seed 42、左右拆分 → 23 层 PSD → image2live2d 自动绑定和原生 MOC3 导出。
自动绑定工具：https://github.com/Wzhang3912/image2live2d
版本：b3fea7536f2d680897dbf5cce5a13046da75803c。
拆层工具：https://github.com/shitagaki-lab/see-through

验收：32 个绘制部件、38 个参数；在本项目已有 Cubism Core 中加载成功。
分别渲染了张嘴、闭眼、转头；初版只适合小幅动作。
V2 修正了裙腰与上衣的遮挡顺序；待机动作减小幅度，眨眼间隔改为不等长的 12 秒循环。
已知限制：拆层降低了脸部细节，头发边缘仍有少量毛边；不是人工精修商用模型，也不包含 Cubism 编辑工程 .cmo3。

桌宠运行时另外提供嘴型平滑（45 ms 时间常数、收到停止立即归零）和头像/名字间距修正，这两项属于播放器，不在模型 ZIP 内。

主图生成提示词见项目 `docs/CHANGZHENG-MODEL.md`。
