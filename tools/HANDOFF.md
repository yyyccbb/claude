# 节拍工具 · 会话上下文交接（2026-11-02）

> 用途：转到本地 Claude Code 继续调整时，先读本文件。仓库 `yyyccbb/claude`，分支 `claude/dazzling-cray-nbi5k2`。
> 两个工具都是单文件 HTML，无构建步骤，双击即用；所有口径来自最终版《节拍分析表》9.2 区公式。

---

## 1. 交付物

| 文件 | 内容 | 状态 |
|---|---|---|
| `tools/takt-checker/index.html` | 线体节拍快速核对网页：选线型 → 出采集清单 → 填数 → 节拍图/瓶颈工序/平衡数据；产能核算选填 | 完成，已与 Excel 缓存值核对一致 |
| `tools/line-sim/index.html` | 自粘钢固化线零件/工装流转模拟：平面布局动画、倍速、运行时间、表格录入、AI/本地指令干预、结构可编辑 | 完成 v2 |
| `tools/line-sim/ai-proxy.js` | 本地 CORS 转发（Node 无依赖），浏览器直连大模型被跨域拦截时用 | 完成，未连真实接口测试 |

源数据：5 份最终版节拍分析表（★定子/转子自粘钢固化线、★定子铁芯焊接线、★带工装流转线、★转子检测线）+ 最新上传的定子自粘钢固化线表（T_ch 1200、上料 80）。上下文压缩版见项目早期《节拍分析表 · 会话上下文压缩版》。

---

## 2. 节拍核对工具（takt-checker）

### 结构
- `TYPES` 数组定义 5 种线型：`cureS` 定子自粘钢固化线(N=1) / `cureR` 转子自粘钢固化线(N=6) / `weld` 焊接线·独立检测线 / `ring` 焊接线·带工装流转线 / `rinsp` 转子检测线(单/双列)
- 每个线型：`sections[]`（字段 `num/sel` + 可选 `table`）+ `compute(v, T)` 返回 `{stations, segs, LT, seg, checks, capChecks, diag}`
- `segs` 按 Excel「约束来源」判定顺序排列，`pickSeg` 取第一个等于最大值的段
- 产能核算 `CAP_SEC`：填「客户月度需求」才生成（TT、TT×OEE、DT、JPH、日/月产能、缺口、余量、超目标工位数 + 线型专项反算）
- 线平衡：工位口径同 Excel J 面板，LBR = ΣCT/(n×工位瓶颈)，另给「按实际 LT 的平衡率」；LT 高于山积图最高工位时提示「隐形瓶颈」（如工装数）
- 输入按线型存 `localStorage`（`lsx-takt-<id>`）；「载入分析表现有数据」仅固化线两型有（`DEMO`）
- 图表：内联 SVG 山积图（作业/流转/周期摊销堆叠 + LT/TT/目标/DT 四条线），无外部依赖

### 核对结果（与 Excel 缓存值一致）
- 定子固化（旧数据）：LT 120（上料瓶颈），月产能 15444，工装最少 24，通道最少 10
- 转子固化：LT 21（冷却段）
- 带工装流转线：LT 250.75（工装数约束），最多焊 5 次，单次上限 41.95 s
- 独立检测线、转子检测线：表内无实测数据，仅用自编数据跑通

---

## 3. 流转模拟（line-sim）

### 模型（模板拓扑，各段内容可改）
```
上料段工位链 pre[]（按工装，第一个工位装 N 件）
 → 进料主通道（dispatch 派发；channels[i].tin 输送时间；最小间距 feedGap）
 → 并联通道 channels[] × 通道内工位序列 chStages[]（chIndex: sync 同步指进 / async 各位独立放行）
   每通道有「入口等待位」：工装提前到位，通道远近只产生延时不占产能（同 Excel 口径）
 → 出料主通道（tout，outGap）→ 脱模 demold（N 件进冷却通道；空工装经回流 ret 秒回上料段）
 → 冷却通道 cool（rows×cols，每组 grp 件；入口组装满且出口组取空后整体前移 fwd 秒；cool.on=false 跳过）
 → 检测线上料机械手 loader → 同步检测线 insp（全部工位做完才一起移栽 move 秒）
 → 人工段工位链 post[]（pack:true 的工位叠加每件/每层/每箱周期动作）→ 成品
```
- 放行时间 TimeSpec：`{type:"fixed",v}` / `{type:"uniform",min,max}` / `{type:"normal",mean,sd}` / `{type:"tri",min,mode,max}`；固定值叠加全局波动系数 `vari`；理论节拍取均值
- 布局：`layout.mirror`（流向右→左，坐标经 `X()/RX()/PX()` 镜像，文字不翻转）、`layout.ch1`（near/far）
- 仿真：固定步长 `DT=0.5s`，每帧按倍速推进（上限 6000 步/帧）；`step()` 下游先行（人工段 → 检测 → 机械手 → 冷却 → 脱模 → 出料 → 通道 → 进料 → 上料段 → 回流）
- 停机：`S.down[id] = {until, reason}`，到期自动恢复；工位 id：上料/人工段用各自 id，通道工位 `ch{i}.{k}`（k 从 1），整通道 `ch{i}`，另有 `feed/out/demold/ret/cooler/loader/insp/insp{j}`；兼容别名 `ch1.heat→ch1.1`、`ch1.cool→ch1.2`
- 配置修改统一走 `patchCfg()` → `normCfg()`；`structSig()` 变化即重建模拟（重新爬坡），时间/参数类即时生效；工装数增减走 `setTools()` 在线增减
- 配置存 `localStorage` 键 `lsx-sim-cfg2`；AI 设置存 `lsx-sim-ai2`
- 导入 xlsx：按需加载 SheetJS（cdnjs 0.18.5），读「9.2 基础数据录入」固化线 15 列版固定单元格（E26/E25/E27、C36:E45、E48/E49、E57/E59/E61/E67/E69、E82–E93、E100、C102:E107、E116–E120、C125:F134、E10–E15）

### 指令与 AI
- 动作协议（AI 与本地解析共用 `applyAction`）：`stop / resume / set / set_time / patch / insert / remove / channel_on / channel_off / speed / run / pause / reset / fast_forward`，任意动作加 `at`（分钟后执行）
- AI 只输出 JSON `{"reply":..., "actions":[...]}`；系统提示 `AI_SYSTEM` 说明模型拓扑与规则；每次请求附 `stateBrief()`（实时状态、工位负荷、可用 id、放行时间清单、数值参数清单、完整配置）
- 接口：`openai`（MiMo / OpenAI 兼容，`POST {base}/chat/completions`，Bearer 鉴权，先带 `response_format: json_object`，400/422 时去掉重试）；`claude`（官方 SDK 0.135.0 经 jsdelivr ESM 按需加载，`claude-opus-5-5`，`fallbacks:"default"`）
- 无 Key 或调用失败 → `localParse()` 本地规则；已覆盖：通道停机/恢复（按工位名）、通道工位序列增删改（“变成 A-B-C”）、放行时间区间/正态/固定、上料段/人工段插入删除工位、流向镜像、1#通道位置、同步/独立放行、开关冷却通道、派发策略、工装数、倍速、延时执行

### 验证结果
- 默认结构（T_ch 1200、9 通道）无波动跑 10 h：平均 133.25 s/件 = 理论 133.3（固化段）
- 改为 加热固化→冷却1(900~1000 s)→冷却2、各位独立放行：134.2 s/件，瓶颈仍在固化通道
- 转子工况 N=6：模拟 24.0 vs 理论 23.6（冷却按组前移与上料机械手互相牵制，静态表算不出）
- 实际冷却时间约 4900 s，表中按「容量×LT」为 6400 s（出口组取空才前移，通道实存约 42 件）
- 13 条典型中文指令本地解析全部正确；AI 链路仅用模拟接口验证，**未用真实 MiMo Key 跑过**

---

## 4. 待办 / 未确认

1. **MiMo 接口细节未核对**：`https://mimo.mi.com/docs/zh-CN/quick-start/summary/welcome` 在云端环境被网络策略拦截。默认值 `https://api.xiaomimimo.com/v1`、`mimo-v2-flash` 为推测（仓库仅确认 `mimo-v2-flash` 为自部署服务名），本地需按控制台核对：base URL、模型 ID、是否支持 `response_format`、是否返回 `reasoning_content`/需关闭思考、是否允许浏览器跨域
2. 真实 Key 下测试：结构修改类指令（patch chStages 等）模型输出是否稳定为合法 JSON；必要时在 `AI_SYSTEM` 补示例
3. 本地规则新增「冷却2」时沿用原冷却位 1200 s，若实际不同需再下指令改
4. 模拟器只覆盖自粘钢固化线拓扑；焊接线（独立检测线/工装环线）、转子检测线（单/双列、冲床连线、夹爪合流）如需模拟要另建流转逻辑
5. 节拍核对工具：焊接线、转子检测线待现场实测数据回填后再核一次
6. 布局为按工艺流程自动生成的示意图，非现场真实平面布置；如需按实际布局，需提供布局图后加坐标配置

---

## 5. 本地调试

```bash
git fetch origin claude/dazzling-cray-nbi5k2
```
```bash
git checkout claude/dazzling-cray-nbi5k2
```
- 直接双击 `tools/line-sim/index.html` / `tools/takt-checker/index.html`
- 跨域时：在 `tools/line-sim` 下运行（Windows 改目标用 `set AI_TARGET=https://...`）：
```bash
node ai-proxy.js
```
- 浏览器控制台可直接调用：`localParse("…")`、`applyAction({...})`、`fastForward(秒)`、`theory(CFG)`、`avgTakt()`；无波动对照：`CFG.vari=0; resetSim(); fastForward(10*3600); avgTakt()`
- 回归测试做法：Playwright 打开页面 → `fastForward` 若干小时 → 对比 `avgTakt()` 与 `theory(CFG).LT`；AI 用 `page.route('**/v1/chat/completions', …)` 返回固定 JSON 验证执行链
