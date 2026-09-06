# N.E.K.O 直播模式：源码核查

核查时间：2026-09-06。固定版本：[`e1fa3482509132532a242d841b98d55ba03d4c4b`](https://github.com/Project-N-E-K-O/N.E.K.O/tree/e1fa3482509132532a242d841b98d55ba03d4c4b)。只读官方仓库，没有安装、运行 NEKO 或验证它的线上专用服务。

**建议：小征继续用现有引擎，借弹幕选题、播放确认、动作变体三块。不要为了声音直接整体换 NEKO；它的直播原生语音优势依赖专用上游，源码开关本身不能提供那个音色或服务。**

## 先分清两个“直播”

源码的 `livestream_mode` 是 `core_api_type='free'` 上的专用服务子模式；B站弹幕插件是另一条独立输入链。开专用服务模式不等于自动接入弹幕，也没有看到这个布尔开关创建一套独立主播人格/公开记忆库。

- **代码已实现**：配置需 `enabled=true` 且 `server_prefix` 非空；重写 free 路径的 `/core`、`/text/v1`、`/tts`，允许指定 `voice_id`，跳过 free/GLM 通常的90秒无语音自动断会话。见 [配置读取 L544–591](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/utils/api_config_loader.py#L544-L591)、[路由 L750–795](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/utils/config_manager/core_config.py#L750-L795)、[静默判断 L345–357](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/main_logic/omni_realtime_client/_client.py#L345-L357)。
- **代码已实现**：语音对话的 livestream 路径直接关闭客户端外部 TTS，采用服务端原生语音；配置的直播 voice 可绕过普通预设音色限制。**源码注释声称**上游为 Gemini → core_proxy → CV3 真双向流式，这部分不能从客户端代码证明线上服务可用或其性能。见 [TTS 分流 L1417–1431](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/main_logic/core/tts_runtime.py#L1417-L1431)、[voice 解析 L1514–1547](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/main_logic/core/tts_runtime.py#L1514-L1547)。这不是我们现有 SiliconFlow CosyVoice2 接口的可直接替换配置。

## 弹幕实际怎样处理

`DanmakuListener` 经B站 WSS接收，解析压缩包和 `DANMU_MSG`；插件过滤空文本、屏蔽用户，再写显示队列、分析队列和 SQLite。普通事件入口传给分析器的 `guard=0/admin=False`，因此不能把评分器“支持舰长/房管权重”误写成此路径实际完整用上。见 [接入核心 L79–133](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/danmaku_core.py#L79-L133)、[真实入队入口 L1629–1708](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/__init__.py#L1629-L1708)。

| 路径 | 源码实际行为 |
|---|---|
| 背景 LLM | 配置默认20秒窗口，最多30条采样；增强 Agent 再累积到20条才调筛选 LLM，选1–3条。池上限500，超限去掉最旧；成功或失败都清空池。未凑够数量时跳过本地评分。**推断：低流量房间可能等很久才回应；窗口不是延迟上限。** |
| Legacy 降级 | 队列上限200；每批一次取空，合并重复、按问题/情绪/等级评分，只推前2条；全是哈哈/666等轻互动就跳过；SC展示至多3条，其余只计数。未选内容不逐条补答。 |
| 空闲 | 增强 Agent 无批次时查静默，默认300秒后向主角色推“可以随便聊点别的”提示，有冷却；Legacy无数据直接返回。不能说两条路径都自动暖场。 |
| 主角色正在说话 | 插件先生成提示，再由通用交付管理器排队；实际播放没结束或主模型还在生成就不注入。按优先级/FIFO整批释放到下一轮，默认90秒TTL；显式同键可合并，队列超限会淘汰。高优先级不等于强行打断声音。 |

证据：[聚合器 L198–222](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/aggregator.py#L198-L222)、[Agent 数量池 L347–397](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/background_llm_agent.py#L347-L397)、[Legacy L2066–2143](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/__init__.py#L2066-L2143)、[静默 L834–849](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/background_llm_agent.py#L834-L849)、[默认配置](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/data/config.json#L1-L25)、[播放门控 L803–862](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/main_logic/proactive_delivery.py#L803-L862)。

另一个限制：Agent 的批次队列本身是无界 `asyncio.Queue()`，不是所有层都有限流；待机时 `feed_batch` 直接丢弃分析数据。因此不能把它描述为“全部消息可靠排队无损”。[队列 L163–167](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/background_llm_agent.py#L163-L167)、[待机 L230–236](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/background_llm_agent.py#L230-L236)。

## 人设、记忆、权限和普通聊天的区别

**代码已实现**：弹幕筛选 Agent 是幕后助手，有房间话题/密度记忆、用户画像和本地昵称，后台记忆落 `data/agent_memory`；筛完后通过 `push_message(ai_behavior='respond', target_lanlan=...)` 投给所选现有角色，由角色真正回答，不直接朗读筛选器结果。普通和主动回合共用后续表情流程；主动回合不自动放音乐，也不自己继续触发下一轮主动聊天。见 [Agent 初始化 L1185–1232](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/__init__.py#L1185-L1232)、[角色交付 L4010–4037](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/plugins/bilibili_danmaku/__init__.py#L4010-L4037)、[共用收尾 L1472–1482](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/app/app-websocket.js#L1472-L1482)。

**范围内未找到**：livestream 开关带来独立的公开/私聊记忆隔离或工具权限收缩。插件还提供发弹幕、评论、动态、私信的独立入口；“主人账号”识别可帮助代写指令，但不能据此证明所有观众输入在权限层都受限。小征现有公开/私聊边界应保留，不能假定换引擎自动获得。`visibility=[]` 仅决定插件内容是否渲染，`respond` 仍会送入主模型。[桥接语义 L38–53](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/plugin/server/messaging/proactive_bridge.py#L38-L53)。

## 声音、表情和动作怎样配合

**代码已实现**：前端以 `turn_id/speech_id` 管音频队列，用实际播放开始/结束信号通知后端；口型采样 WebAudio 波形 RMS，乘10限幅再做0.5平滑。这是振幅口型，不是音素或语义级口型。[播放开始 L700–716](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/app/app-audio-playback.js#L700-L716)、[口型 L1484–1516](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/app/app-audio-playback.js#L1484-L1516)。

表情在回合文本收尾时异步分析整段，最多等5秒，再调用 `applyEmotion`；并非每个重音都与动作严格对齐。Live2D按情绪随机选已有motion/expression；相同情绪+表情有50%概率再播动作；没有资源时退回简单点头/低头。要更丰富仍需模型里的动作/参数映射。范围内没看到直播专用 Neuro 式连续蹦跳控制器。[情绪分析 L1511–1529](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/app/app-websocket.js#L1511-L1529)、[随机动作 L1191–1204](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/live2d/live2d-emotion.js#L1191-L1204)、[动作后备 L1331–1367](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/live2d/live2d-emotion.js#L1331-L1367)、[同情绪随机 L1512–1525](https://github.com/Project-N-E-K-O/N.E.K.O/blob/e1fa3482509132532a242d841b98d55ba03d4c4b/static/live2d/live2d-emotion.js#L1512-L1525)。

## 小征最值得借的五项

1. **选题优先于逐条回复**：在现有 `LiveInbox` 去重/15秒TTL上增加“直接问题、当前话题、趣味性”的简单评分，只取1–2个。无需再串一个 LLM，更适合当前低流量和降延迟诉求。
2. **用实际播放完成释放下一次回应**：保留小征已有播放确认，补充可观察的排队/过期原因即可。不要复制 NEKO 整套总线，也不要用TTS生成完成冒充播放结束。
3. **同情绪多个动作变体**：借随机选择和不覆盖进行中动作的办法；小征已有音量驱动的轻弹跳可继续保留，动作资源不足时优先做2–3个自然变体。
4. **冷场提示与正常回应分开**：看最近弹幕、上次说完时间和已有话题，稀疏主动开口；不要照搬20条池阈值或20秒窗口，也不要每次问“大家还在吗”。
5. **长远研究真正双向流式语音**：先解决当前句子切分和现有服务尾延迟；只有拿到兼容服务并实测首音频/连续播放收益后，才考虑替换语音管线。NEKO 的服务端路径是参考架构，不能视为现成可用的免费语音能力。

上述是基于固定源码的工程建议，未运行 NEKO；没有对其真实直播声音、观众端延迟或部署稳定性作体验保证。
