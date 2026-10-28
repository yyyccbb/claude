# 工具链规范与 LSX 内部风格

> 注：原 claude.ai 沙箱路径（/mnt/project、/mnt/user-data、/home/claude）在 Claude Code 中不存在；PPT 模板已随包放在 `templates/`，其它源文件需自行放入仓库。

## PPT — LSX 标准
- 工具：pptxgenjs（Node.js）；模板 `templates/LSX_PPT_gen_template.js`，前 142 行为可复用函数：makeCover、makeTOC、makeSection、makeContent、makeTable、makeEnding、addLogoSmall、addHeaderLine、addTitleBar、addBand
- 底部色带：`ppt底部色带.png` 原图，全宽 1919×12px，h=57180 EMU（0.0625"），y=5086320 EMU（5.5625"），w=10"
- 字体：正文/标题→微软雅黑（macOS: PingFang SC），数据/表格→Arial，庄重/古典→黑体；中文主题字体=微软雅黑
- 配色：navy #002060、blue #1F61A8、red #C00000；整体浅色（白底+浅灰点缀）
- 封面：白底 + 右侧浅灰区（x=7.2, w=2.8）+ 蓝色竖线 + 左上 logo + 主标题 60pt navy + 副标题 24pt blue
- 章节/结尾页：白底 + 左侧三色条（navy 0.22" + blue 0.07" + red 0.04"，满高）+ 浅灰内容框（x=0.5, y=0.95, w=9.1, h=3.85）+ 水印数字 110pt 78% 透明 + 蓝色分隔线 x=3.0 + 章节标题 34pt
- 内容页：白底 + 页眉线（y=0.82）+ 右上 logo（x=7.6, y=0.12, w=2.2, h=0.39）+ 左侧蓝条 0.06" + 要点文字 + 右侧数据卡（浅灰 F2F4F7 + 顶部色条）
- 表格：navy 深蓝表头 + 白字 + 灰白隔行
- 不用深色背景页；底部色带全宽贴底
- 客户版 PPT 也用过另一套配色：navy 1E3A5F / steel 4A6FA5 / amber E8871E

## WI 作业指导书规范
- 模板：`PM定子返工.docx` —— 直接改 XML，保留页眉页脚/logo/样式
- A4 纵向；3 列表格（序号 | 操作描述 | 示意图）；图片从源 PPT 页面提取
- 安全提示以"注意："写在描述内，不单列；底部不加文件信息表
- 封面（版本记录 + FMEA/控制计划勾选 + 审批签字）与步骤内容用分页符隔开

## 节拍分析 skill
- 位置：`.claude/skills/line-takt-analysis-2-0/`
- 依次运行 `analyze_interval.py` → `build_dashboard.py`，输出 HTML 看板（可选 `build_excel_chart.py` 生成 Excel 散点图）
- 打包：`cp -r` 到暂存目录 → `zip -r` → 复制到输出目录

## Excel / 数据工具
- `.xlsx` 用 openpyxl；老 `.xls` 用 xlrd（`formatting_info=True`）+ xlutils/xlwt
- DOCX：`docx` npm 库（Node.js），字体 SimSun/SimHei，A4
- 扫描件 PDF：从 ZIP 结构中按顺序提取 JPEG
- LibreOffice（soffice）转 PDF；`pdftoppm` 渲染 JPEG 做 QA

## 节拍分析表模板（Bosch BPS）
- 使用 Bosch Powertrain Systems | PS/BPS Version 3.0《Takt Time Chart》.xls，三张表：`Process confirmation`（输入）/ `9.1 Data for Takt Time Chart`（中间层）/ `9. Takt Time Chart`（山积图）
- 实例：`H10-1金康SHG85_焊接线OBC2024_7_3.xls`（P33A 定子焊接线，planner 吴颖，Foreman Yang）
- 已做成四类节拍分析表：定子自粘钢固化线、转子自粘钢固化线、定子铁芯焊接线、转子检测线（口径见 line-takt-models.md）
- 统一结构：`过程确认`（展示 + 红框每月实测）/ `9.1 节拍图数据` / `9. 节拍图`（山积图）/ `9.2 基础数据录入`（唯一录入口），全表中文

## Albatross 讲座 PPT
- 45 页，定子线（S01–S15）+ 转子线（R01–R12）；布局函数 makeStep、makeImpact、makeFlow、makeQuote
- 每次 `node script.js` 后都要做 OOXML ZIP 顺序修正

## 图纸/产品技术评审流程（2026-09）
- 《新产品图纸/产品技术评审流程_工艺工程师版》（docx）基于三份客户定子图：Tesla 2253931-00-A（激光焊、18 段旋转）、UAES F01RG08C9B11（12 条激光焊缝、端片粘接）、上海电驱动 EV4.500.0980（0.2mm 自粘钢、拔脱力 >6800N）；12 个评审维度 + 检查表，对齐 LSX/QB-PE-01 APQP 第 1–2 阶段
- 公司程序文件 PDF（PE-01/PE-03/GS-02 等）实为扫描 JPEG 的 ZIP 包、.txt 为空 → 解压看图

## 内部文件编号
- 工装管理：LSX/QB-GS-02 —— 检具设计由季亚萍负责；申请单《工装需求申请表》提交工程部
- 调试件：LSX-QB-QA-07-C06 §5.4.3（强制报废处置）
- 工艺参数放行：《制程与工艺参数放行控制程序》
- 应急响应：LSX-QB-QA-13
- 管理职责：LSX/QB-ZH-04
