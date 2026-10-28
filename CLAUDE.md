# LSXNY 项目上下文（设备工程部 · 无锡隆盛新能源）

> 本文件由 claude.ai 项目「LSXNY」的记忆导出（2026-10-27），供 Claude Code 每次会话自动加载。
> 详细资料在 `memory/` 下，按需读取；不要一次全部加载。

## 我是谁
- 杨春彪（Yang CB），无锡隆盛新能源科技有限公司（LSX）设备工程部经理；机械工程背景，2019 入职；PMP、CSPM-2；IATF16949 内审员
- 公司做新能源驱动电机定子/转子铁芯（冲压、激光焊接、自粘钢固化、检测）
- 主要客户：Tesla（CXIM）、联电 UAES、Bosch、BYD、舜驱/达可尔/汇川
- 64 条线：冲压 20、定子焊接 22、转子检测 22（故障跟踪覆盖 73 条）

## 沟通与输出约定
- 全程中文，制造业术语，简洁直接；我纠正时简短，直接改即可
- 要"拿来就能用"的成品：会议用 Excel、客户 PPT、WI 格式 Word
- 管理汇报用"问题诊断"框架，不要描述性趋势罗列；跟踪类内容优先表格而非卡片
- 每份报告独立成篇，不引用旧版本
- 复刻格式时逐项匹配全部样式（XF 样式、行高、列宽、合并单元格）
- Excel 文件名用英文（避免编码问题）
- 中间 DataFrame 存 `.pkl`；给 Node 构建脚本的图表数据用 JSON
- 绝不编造试验记录；5Why 区分"发生链"与"流出链"，根因指向系统/机制缺陷而非个人

## 关键技术坑（必读）
- 产线 CSV 数据列数多于表头列数 → 用 `codecs` 逐行拆分，不要 `pandas.read_csv()`；编码多为 GBK/GB18030；总成结果在索引 5（0 基）
- Excel 中 `""=0` 为 FALSE（LibreOffice 为 TRUE）→ 长度为 0 的校验段要加 `IF(length=0,1,...)`
- pptxgenjs 生成的文件有时 PowerPoint 打不开 → 大文件需修正 ZIP 顺序（`[Content_Types].xml` 放首位、STORED 不压缩）；从零搭建可改用 python-pptx
- 班次：白班 08:00–20:00，夜班 20:00–次日 08:00；生产"日" = 08:00 至次日 08:00
- 公司程序文件 PDF 实为扫描 JPEG 的 ZIP 包（.txt 为空）→ 解压看图

## 资料索引（memory/）
| 文件 | 内容 |
|---|---|
| `memory/overview.md` | 部门人员、在办事项、组织调整、近期计划 |
| `memory/line-takt-models.md` | 各线型节拍分析流程与测算口径（焊接线/自粘钢固化线/转子检测线/Z7/Z16/Z17） |
| `memory/tools-and-templates.md` | LSX PPT 规范、WI 规范、节拍分析表（Bosch BPS）、内部文件编号 |
| `memory/technical-learnings.md` | 节拍分析、数据解析、焊接/计量的经验结论 |
| `memory/tpm-system.md` | Tesla T-QMS 模块9 TPM 体系、工时、KPI、原因代码 |
| `memory/quality-history.md` | 铁芯质量分析、焊接放行文件历史 |

## 随包工具
- `.claude/skills/line-takt-analysis-2-0/` — 产线节拍/连续性分析 skill（`analyze_interval.py` → `build_dashboard.py`，输出 HTML 看板）
- `templates/LSX_PPT_gen_template.js` — LSX 标准 PPT 模板（前 142 行为可复用函数：makeCover/makeTOC/makeSection/makeContent/makeTable/makeEnding 等）
