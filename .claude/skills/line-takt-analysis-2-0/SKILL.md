---
name: line-takt-analysis-2-0
description: (v2.0) Analyze production-line takt time (节拍) and continuity from equipment log CSVs (columns like 下线时间/时间 and 合格结果/测试总结果, one row per completed part). Computes the theoretical takt time via rolling-window stability analysis, classifies each inter-part interval as normal/degraded/abnormal-pause/line-stop, and produces an interactive HTML continuity dashboard (30-minute-bin overview with a 理论节拍 KPI card, horizontal-scroll section ①) plus a 660/690/720-minute per-shift 开线时间 classification, and optionally a native Excel scatter chart. Use this whenever the user uploads a line/设备/线体 production record CSV and asks about 节拍, 生产连续性, 停机, 停线, 下线间隔, 开线时间, or "帮我分析一下这条线" — even if they don't use the word "skill" or name this skill directly. Also use for follow-up requests to re-run, adjust thresholds, or regenerate the dashboard for a different line's CSV in the same style as before.
---

# 产线节拍与连续性分析

Reusable workflow for analyzing production-line equipment logs: discover the
theoretical takt time, classify every inter-part interval, and produce a
report the user can hand to their team or open in Excel.

## When to use this

Trigger whenever the person gives you a CSV (or similar tabular export) of
per-part production records from a manufacturing line — typically columns
for a completion/下线 timestamp and a pass/fail result (OK/NG) — and asks
about takt time, continuity, stoppages, or wants "the same kind of analysis"
as a previous line. Different lines will have different CSV column names,
different takt times, and possibly different channel configurations (single
vs. shared dual-channel) — re-derive everything from the data each time;
don't assume this line's specific numbers (17s takt, 40s pair-sum threshold,
etc.) apply to a new CSV.

## Workflow

### Step 1 — Inspect the CSV first

Column names vary between exports. Before running anything, peek at the
actual header row (`view` the file or a quick `pd.read_csv(...).columns`)
to find the timestamp column and the OK/NG result column. Common names seen
so far: `时间`/`下线时间` and `测试总结果`/`结果`. Pass the actual names via
`--time-col` / `--result-col` if they differ from the scripts' defaults.

### Step 2 — Discover the theoretical takt + get diagnostics

```bash
python scripts/analyze_interval.py --csv "<path>.csv" \
    --time-col "时间" --result-col "测试总结果" \
    --out-json /tmp/data.json --stop-sec 300
```

This prints:
- Basic counts (total / OK / NG / NG rate / time span)
- Interval percentiles
- The 15 most frequent interval values (rounded, ≤90s) — **look at this for
  a bimodal pattern** (a short cluster + a long cluster). That's the
  signature of a shared dual-channel line (two stations/heads feeding one
  discharge port with interleaved timing) — see Step 3.
- A rolling-window scan (window sizes 15/20/30/50) that finds the most
  regular + stable + fastest segment in the data and reports its mean as
  the candidate theoretical takt, plus how consistent that candidate is
  across window sizes (this is the "规律、稳定、平均最短 = 理论节拍" logic
  the user validated by hand on the first line — see
  `references/methodology.md` for the full derivation and worked example).
- It also writes `data.json`, which the dashboard/Excel builders consume.

**Read the printed report and reason about it before moving on** — don't
just take the single suggested number at face value if the spread across
window sizes is flagged as inconsistent; cross-check against the interval
distribution.

### Step 3 — Decide: dual-channel or single-channel line?

- **Bimodal distribution + rolling-window takt ≈ half of the long-cluster
  value** → shared dual-channel line. The "two consecutive parts" pattern:
  a short interval (one channel firing right after the other) alternates
  with a longer interval (waiting for the slower channel), and *adjacent
  pairs sum to roughly 2x the takt*. Use `--mode dual` in Step 4.
- **Single, fairly tight cluster of interval values near the takt** →
  ordinary single-channel line. Use `--mode single`.

If it's genuinely ambiguous from the data, ask the user briefly (e.g. "这条
线是双通道共用一个下料口吗？") rather than guessing — the classification
tiers depend on it.

For a dual-channel line, also decide the pair-sum threshold: it should sit
comfortably above the typical (short + long) sum but below double the takt
during a degraded/single-channel period. On the reference line analyzed so
far, takt ≈ 17s, normal pairs summed to ~30-40s, and single-channel-only
operation ran close to ~35s per part — so `--pair-sum-max 40` and
`--single-max 45` were used. Re-derive these from the new line's own
percentiles (Step 2 output) rather than reusing these exact numbers.

### Step 4 — Build the dashboard

```bash
python scripts/build_dashboard.py \
    --data-json /tmp/data.json \
    --out-html "/mnt/user-data/outputs/<线体名>_生产连续性分析.html" \
    --title "<线体名> 生产连续性分析" \
    --mode dual --pair-sum-max 40 --single-max 45 --stop-sec 300 --takt 17
```

(Use `--mode single --single-max <takt*~1.3>` for a single-channel line —
omit `--pair-sum-max` in that case, it's unused.)

The generated HTML is a self-contained artifact with:
1. **30-minute-bin overview** — parts-per-bin bar chart, colored by
   output level, red dot = bin contains an NG. Bin width defaults to 30
   minutes; override with `--overview-bin-min <N>` if the user wants a
   different granularity (e.g. `--overview-bin-min 5` for a finer view).
2. **Per-part interval detail** (bar chart, toggle to a cumulative-count-vs-
   time line chart) — colored by the 4-tier (or 3-tier for single-channel)
   classification, NG parts marked red, stoppages clipped/annotated.
3. **Stoppage event table** — every interval over `--stop-sec`, sorted by
   duration, for root-cause traceback.

Copy the output to `/mnt/user-data/outputs/` and call `present_files` on it
— don't just leave it in the working directory.

### Step 5 — Excel version (only if asked)

If the person wants the chart in Excel instead (e.g. "放Excel，我要自己调整
坐标间隔"), use `build_excel_chart.py` instead of / in addition to the HTML
dashboard:

```bash
python scripts/build_excel_chart.py --csv "<path>.csv" \
    --out-xlsx "/mnt/user-data/outputs/<线体名>_累计产量-时间折线图.xlsx" \
    --time-col "时间" --result-col "测试总结果"
```

This produces a native Excel scatter/line chart (X = cumulative count,
Y = timestamp, NG overlaid in red) with axis intervals the user can adjust
themselves in Excel (right-click axis → 设置坐标轴格式 → 单位). Read the
gotchas in the script's docstring before hand-editing this chart — both
were real bugs hit and fixed during development (broken Y-range from
including the header row; wrong axis-unit magnitude from treating a date-
serial NumericAxis's `majorUnit` as literal minutes instead of a fraction
of a day).

## Company shift/day convention

LSX runs two shifts: 白班 08:00–20:00, 夜班 20:00–次日08:00. A production
"day" (一天) therefore runs **08:00 to next day 08:00**, not midnight to
midnight — keep this in mind when binning by day, labeling date ranges in
report titles/subtitles, or splitting a CSV that spans a natural day
boundary into shifts.

## 开线时间统计（每班次生产时长判定）

按班次（白班08:00-20:00 / 夜班20:00-次日08:00）逐班判定，而不是按自然天。
每班理论时长12小时=720分钟。

**吃饭窗口（各线交替吃饭，每条线在每个窗口内停机约30分钟）：**
- 白班：11:00–12:30、16:30–18:00
- 夜班：23:00–00:30、04:30–06:00（相对班次起点的偏移与白班一致，错后12小时）

**判定规则（先确认该班是否整班运行，再判两次吃饭窗口内的停机情况）：**

1. **标准班（660分钟）**：两次吃饭窗口内该线均有≈30分钟的生产停止记录
   （正常吃饭停线）。720 − 30 − 30 = 660。
2. **单次未停餐（690分钟）**：两次窗口中只有一次生产记录未完全停止
   （该线这一顿没停），记为独立的第4类，690 = 660 + 30。**不要**并入
   660或720，也不要归入临时生产。
3. **换班/连续生产（720分钟）**：两次窗口生产记录均未停止，即整班没有
   吃饭停线，记满整班720分钟。
4. **临时生产**：该线在这个班次内并未按整班08:00-20:00或20:00-08:00
   运行，而是中途开始或中途结束（以线体实际起停时间为准，而非套用
   660/690/720模板）。这种情况一台机一天通常只出现1~3次；如果同一
   线体在同一班内频繁启停（明显多于3次的开-停循环），大概率是设备
   故障维修导致的中断，应在报告中单独标注为"疑似故障停机"而非正常的
   临时生产，不要计入开线时长统计的分母。

**每班次开线时长的判定结果只会落在以下4类之一：**
660分钟 / 690分钟 / 720分钟 / 临时生产（含疑似故障标注）。

**开机延迟/交接班停机的处理**：班次起点/终点前后的短暂延迟（如实际首件
比班次起点晚一小段时间、末件比班次终点早一小段时间）、以及白班→夜班
交接时段的停机，属于常规组织损失（换班交接、准备工作等），**不从开线
时长里扣除**。只要两次官方吃饭窗口内该线均未停线，就记为720分钟——
不用管窗口之外出现的零散停机（无论是交接班停机还是窗口附近的临时
停机）。窗口之外的停机只在故障/停线事件清单里单独体现，不影响
660/690/720/临时生产这套开线时长分类。

**这套判定逻辑已在 `build_dashboard.py` 中自动实现（`_infer_shift_kpis`）**：
根据 data.json 里每条记录的时间戳，自动切出数据覆盖的每个班次（按
08:00/20:00 边界），逐班判定 660/690/720/临时生产，并作为独立的
"当班生产时间推测"KPI卡片渲染在头部汇总区（每个班次一张卡）。判定用到
两个可调阈值，写死在脚本顶部，如需调整直接改常量即可：
- `MEAL_STOP_SEC`（默认900秒/15分钟）：吃饭窗口内出现的最大间隔要
  达到这个值才判定"该窗口真的停线吃饭"。
- `SHIFT_TOL_SEC`（默认3600秒/1小时）：班次首/末件相对班次边界的
  容忍延迟，超出此容忍度就判定为"临时生产"（非整班运行），而不是
  硬套660/690/720模板。
不需要用户在命令行传参，脚本会自动从 `--data-json` 里的记录时间戳
推算——如果以后要改成命令行可调，再加对应的 `--meal-stop-sec` /
`--shift-tol-sec` 参数即可。

## Known gotchas (already fixed in the scripts — don't reintroduce)

1. **Timezone bug**: `data.json` timestamps are epoch-ms derived from the
   naive CSV timestamp taken as-is (no timezone applied). The dashboard's
   JS **must** format them with `getUTC*` methods (`getUTCHours`,
   `getUTCMinutes`, etc.), never the local `get*` variants — otherwise the
   displayed time shifts by the difference between the server's timezone
   (this environment runs UTC) and the viewer's browser timezone, making
   the whole time axis wrong. `build_dashboard.py` already does this
   correctly; if you hand-edit the template, preserve it.
2. **Excel header-row-in-range bug**: any `Reference` used as chart Y
   values must start at the same row as the X values (skip the header).
   Including the header text as a data point silently corrupts the axis
   scale in Excel/LibreOffice.
3. **Excel axis-unit-magnitude bug**: on a `ScatterChart`, `y_axis` is a
   `NumericAxis`. If the Y values are datetimes, `majorUnit` must be
   expressed in *days* (Excel's native date-serial unit), e.g. 30 minutes
   → `30/1440`, not the literal integer `30`.
4. **Copyright / privacy**: this is the user's own factory-floor equipment
   data — no copyright or external-privacy concerns apply, proceed
   normally without the usual citation/quoting caution.
5. **Dashboard layout requirements (already fixed — don't regress)**:
   - When `--takt` is passed, the KPI row **must** include a "理论节拍"
     card (leftmost, showing the value in seconds) — this is generated
     automatically by `build_dashboard.py`; don't drop it if you hand-edit
     the template.
   - Section ①（30-minute-bin overview chart, default `--overview-bin-min
     30`）**must** use the `scroll-box` horizontal-scroll container
     (`overflow-x:auto`), never a fixed-width div or a plain table — the
     bin count can be large and needs to scroll rather than compress/wrap.
     Don't silently revert the default bin width back to 5 minutes when
     hand-editing or rebuilding the template.
   - Section ②'s per-part bar chart "标准线"（dashed reference line）
     **must** be drawn at the theoretical takt (`--takt`) when provided,
     labeled `${takt}s（理论节拍）` in navy blue — not at `--single-max`.
     Only fall back to the old `single_max` threshold line (rust color,
     unlabeled "理论节拍") when no `--takt` is given. Don't revert this to
     always using `single_max`.
   - When `--takt`-worthy data is available, the KPI row **must** also
     include one "当班生产时间推测" card per shift covered by the data
     (660/690/720分钟 or 临时生产，per the 开线时间统计 rule above) —
     this is generated automatically by `_infer_shift_kpis()` in
     `build_dashboard.py`, no extra CLI flag needed. Don't drop it when
     hand-editing the template.

## Reference

`references/methodology.md` has the full worked derivation of the takt-time
logic (why rolling-window CV+mean scanning was chosen, the validation against
the dual-classified-interval subset, and the original manual analysis this
was distilled from) if you need to explain the method to the user or adapt
it further.
