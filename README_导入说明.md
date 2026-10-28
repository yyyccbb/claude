# 导入 Claude Code 说明

## 方式一：作为项目目录（推荐）
把整个文件夹内容解压到你的工作仓库根目录：
- `CLAUDE.md` —— Claude Code 启动时自动加载
- `memory/` —— 详细资料，CLAUDE.md 里有索引，按需读取
- `.claude/skills/line-takt-analysis-2-0/` —— 项目级 skill，自动可用
- `templates/LSX_PPT_gen_template.js` —— PPT 模板

## 方式二：全局生效（所有项目都用）
- 把 `CLAUDE.md` 内容追加到 `~/.claude/CLAUDE.md`
- 把 `.claude/skills/line-takt-analysis-2-0/` 复制到 `~/.claude/skills/`
- `memory/` 放到 `~/.claude/lsxny-memory/`，并把 CLAUDE.md 里的 `memory/` 路径改成该绝对路径

## 注意
- 已排除与本项目无关的个人信息（足球、投资）
- 原 claude.ai 沙箱路径（/mnt/project、/home/claude 等）在 Code 中失效；项目里的程序文件、反应计划、线体清单等原件请另行放入仓库
- skill 依赖：Python 3 + pandas（看板），可选 openpyxl（Excel 图）
