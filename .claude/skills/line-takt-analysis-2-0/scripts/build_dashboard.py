#!/usr/bin/env python3
"""
build_dashboard.py — Render the interactive HTML continuity dashboard from
a data.json produced by analyze_interval.py.

Two modes:
  --mode dual   (default) Shared dual-channel line: a part is judged
                "normal" if it and a neighboring part's intervals sum to
                less than --pair-sum-max (interleaved channels). Otherwise,
                if the interval itself is <= --single-max, it's judged
                "single-channel degraded" (still producing, one channel
                down). Above that, up to --stop-sec, it's an abnormal
                pause; beyond --stop-sec it's a line stop.
  --mode single Plain single-channel line: interval <= --single-max is
                normal, up to --stop-sec is an abnormal pause, beyond is
                a line stop. No "degraded" tier.

Usage:
    python build_dashboard.py --data-json data.json --out-html out.html \
        --title "H9 焊接线" --mode dual --pair-sum-max 40 --single-max 45 \
        --stop-sec 300 --takt 17

Colors follow the LSX standard palette: navy #002060, blue #1F61A8,
red #C00000, amber #E8A33D (degraded tier), rust #C0521E (pause tier).
"""
import argparse
import json
import datetime as _dt

MEAL_STOP_SEC = 900       # 吃饭窗口内最大间隔≥此值(15分钟)才判定该窗口"停线吃饭"
SHIFT_TOL_SEC = 3600      # 班次首/末件相对班次边界的容忍延迟(1小时)，视为组织性损失，不算临时生产


def _infer_shift_kpis(records):
    """Infer per-shift production-time classification (660/690/720/临时生产)
    from the raw records, following the meal-window rule documented in
    SKILL.md. Returns a list of (label, value, sub, cls) tuples for KPI cards.
    """
    if not records:
        return []
    dt_list = sorted(
        _dt.datetime.fromtimestamp(r["ts"] / 1000.0, tz=_dt.timezone.utc).replace(tzinfo=None)
        for r in records
    )
    min_dt, max_dt = dt_list[0], dt_list[-1]

    anchor = _dt.datetime(1970, 1, 1, 8, 0, 0)
    shift_len = _dt.timedelta(hours=12)
    idx0 = int((min_dt - anchor) // shift_len)
    shift_start = anchor + idx0 * shift_len

    cards = []
    while shift_start < max_dt:
        shift_end = shift_start + shift_len
        in_shift = [d for d in dt_list if shift_start <= d < shift_end]
        if not in_shift:
            shift_start += shift_len
            continue
        actual_first, actual_last = in_shift[0], in_shift[-1]
        is_day = shift_start.hour == 8
        shift_label = (f"{'白班' if is_day else '夜班'} "
                       f"{shift_start:%m-%d %H:%M}~{shift_end:%m-%d %H:%M}")

        full_cov = (
            (actual_first - shift_start).total_seconds() <= SHIFT_TOL_SEC
            and (shift_end - actual_last).total_seconds() <= SHIFT_TOL_SEC
        )

        if not full_cov:
            mins = (actual_last - actual_first).total_seconds() / 60
            cards.append((
                f"当班生产时间推测（{shift_label}）",
                f"临时生产≈{mins:.0f}分钟",
                f"实际覆盖{actual_first:%H:%M}~{actual_last:%H:%M}，非整班运行",
                "gap",
            ))
            shift_start += shift_len
            continue

        meal_offsets = [
            (_dt.timedelta(hours=3), _dt.timedelta(hours=4.5)),
            (_dt.timedelta(hours=8.5), _dt.timedelta(hours=10)),
        ]
        stopped_flags = []
        for off_s, off_e in meal_offsets:
            ws, we = shift_start + off_s, shift_start + off_e
            pad = _dt.timedelta(minutes=5)
            gaps_in_window = []
            for i in range(len(dt_list) - 1):
                a, b = dt_list[i], dt_list[i + 1]
                if b < ws - pad or a > we + pad:
                    continue
                gaps_in_window.append((b - a).total_seconds())
            stopped_flags.append(
                (not gaps_in_window) or max(gaps_in_window) >= MEAL_STOP_SEC
            )

        n_stop = sum(stopped_flags)
        minutes = {0: 720, 1: 690, 2: 660}[n_stop]
        win_names = ["午餐/餐1窗口", "晚餐/餐2窗口"]
        detail = "，".join(
            f"{name}{'停线' if flag else '未停线'}"
            for name, flag in zip(win_names, stopped_flags)
        )
        cards.append((
            f"当班生产时间推测（{shift_label}）",
            f"{minutes}分钟",
            detail,
            "",
        ))
        shift_start += shift_len

    return cards


def build(args):
    with open(args.data_json, "r", encoding="utf-8") as f:
        data_json = f.read()

    mode = args.mode
    pair_sum_max = args.pair_sum_max
    single_max = args.single_max
    stop_sec = args.stop_sec
    title = args.title

    ref_line_val = args.takt if args.takt else single_max
    ref_line_label = (
        f"┄┄ {ref_line_val:g}s（理论节拍标准线）" if args.takt
        else f"┄┄ {ref_line_val:g}s（单通道/异常停顿分界）"
    )

    if mode == "dual":
        legend_bar = f"""
    <span><i class="swatch" style="background:#1F61A8"></i>双通道正常（相邻两件间隔之和&lt;{pair_sum_max:g}s）</span>
    <span><i class="swatch" style="background:#E8A33D"></i>单通道异常生产（相邻两件之和≥{pair_sum_max:g}s，本件≤{single_max:g}s）</span>
    <span><i class="swatch" style="background:#C0521E"></i>异常停顿（未停线，{single_max:g}s~{stop_sec/60:g}分钟）</span>
    <span><i class="swatch" style="background:#C00000"></i>停线（&gt;{stop_sec/60:g}分钟，已截断）</span>
    <span><i class="swatch" style="border-radius:50%;background:#C00000"></i>NG 品</span>
    <span>{ref_line_label}</span>"""
        desc = (f"柱高 = 与上一件的下线时间间隔（秒）。双通道共用一个下料口、动作交叉："
                f"只要与相邻一件（前一件或后一件）间隔之和 &lt; {pair_sum_max:g}s，判定为双通道正常生产；"
                f"否则若本件间隔仍 ≤{single_max:g}s，说明降为单通道运行（异常但仍在动作）；"
                f"间隔继续拉长视为异常停顿；超过{stop_sec/60:g}分钟记为停线（顶部箭头截断标注）。"
                f"红点 = NG。可切换为折线图（横坐标=累计生产数量，分度值1；纵坐标=时间）")
    else:
        legend_bar = f"""
    <span><i class="swatch" style="background:#1F61A8"></i>正常生产（≤{single_max:g}s）</span>
    <span><i class="swatch" style="background:#C0521E"></i>异常停顿（未停线，{single_max:g}s~{stop_sec/60:g}分钟）</span>
    <span><i class="swatch" style="background:#C00000"></i>停线（&gt;{stop_sec/60:g}分钟，已截断）</span>
    <span><i class="swatch" style="border-radius:50%;background:#C00000"></i>NG 品</span>
    <span>{ref_line_label}</span>"""
        desc = (f"柱高 = 与上一件的下线时间间隔（秒）。间隔 ≤{single_max:g}s 视为正常生产；"
                f"{single_max:g}s~{stop_sec/60:g}分钟视为异常停顿（未停线）；"
                f"超过{stop_sec/60:g}分钟记为停线（顶部箭头截断标注）。"
                f"红点 = NG。可切换为折线图（横坐标=累计生产数量，分度值1；纵坐标=时间）")

    legend_line = legend_bar
    if args.takt:
        legend_line += f"\n    <span>┄┄ 灰色参考线：按{args.takt:g}s/件理论节拍推算</span>"


    classify_js = f"""
const PAIR_SUM_MAX = {pair_sum_max};
const SINGLE_MAX = {single_max};
const STOP_SEC = {stop_sec};
const MODE = '{mode}';
const TAKT_REF = {args.takt if args.takt else 'null'};
const CLASS_COLOR = {{ dual:'#1F61A8', single:'#E8A33D', pause:'#C0521E', stop:'#C00000' }};

function classifyAt(i){{
  const iv = DATA[i].iv;
  if(iv===null) return null;
  if(iv > STOP_SEC) return 'stop';
  if(MODE === 'single'){{
    return iv <= SINGLE_MAX ? 'dual' : 'pause';
  }}
  const prev = i>0 ? DATA[i-1].iv : null;
  const next = i<DATA.length-1 ? DATA[i+1].iv : null;
  const sumPrev = prev!==null ? prev+iv : Infinity;
  const sumNext = next!==null ? iv+next : Infinity;
  const isDual = Math.min(sumPrev, sumNext) < PAIR_SUM_MAX;
  if(isDual) return 'dual';
  if(iv <= SINGLE_MAX) return 'single';
  return 'pause';
}}
const CLASSES = DATA.map((d,i)=>classifyAt(i));
"""

    kpi_single_card = (
        "{label:'单通道异常生产', value: singleChannel.length, "
        f"sub:'相邻两件之和≥{pair_sum_max:g}s', cls:'gap'}},"
        if mode == "dual" else ""
    )

    kpi_takt_card = (
        f"{{label:'理论节拍', value:'{args.takt:g}s', sub:'每件（推算基准）', cls:''}},"
        if args.takt else ""
    )

    try:
        _records = json.loads(data_json)
    except Exception:
        _records = []
    _shift_cards = _infer_shift_kpis(_records)

    def _js_str(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    kpi_shift_cards = "".join(
        f"{{label:'{_js_str(label)}', value:'{_js_str(value)}', "
        f"sub:'{_js_str(sub)}', cls:'{cls}'}},"
        for label, value, sub, cls in _shift_cards
    )

    takt_ref_js = ""
    if args.takt:
        takt_ref_js = f"""
  const AVG_REF = {args.takt};
  const refEndTs = t0 + (n-1)*AVG_REF*1000;
  s += `<line x1="${{padL}}" y1="${{yScale(t0).toFixed(2)}}" x2="${{(padL+(n-1)*stepX).toFixed(2)}}" y2="${{yScale(Math.min(refEndTs,t1)).toFixed(2)}}" stroke="#B9C0CC" stroke-dasharray="5,4" stroke-width="1.3"/>`;
"""

    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<style>
  :root{
    --navy:#002060;
    --blue:#1F61A8;
    --red:#C00000;
    --amber:#E08A1E;
    --card-bg:#F2F4F7;
    --line:#D9DEE5;
    --text:#1A2233;
    --muted:#6B7686;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; padding:24px; background:#FFFFFF; color:var(--text);
    font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
  }
  h1{font-size:22px; color:var(--navy); margin:0 0 4px 0;}
  .subtitle{color:var(--muted); font-size:13px; margin-bottom:20px;}
  .kpi-row{display:flex; gap:12px; flex-wrap:wrap; margin-bottom:22px;}
  .kpi{
    flex:1 1 150px; background:var(--card-bg); border-radius:6px; padding:14px 16px;
    border-top:3px solid var(--blue);
  }
  .kpi.ng{border-top-color:var(--red);}
  .kpi.gap{border-top-color:var(--amber);}
  .kpi-label{font-size:12px; color:var(--muted);}
  .kpi-value{font-size:22px; font-weight:600; color:var(--navy); margin-top:4px;}
  .kpi-sub{font-size:11px; color:var(--muted); margin-top:2px;}

  .section{margin-bottom:26px;}
  .section-title{font-size:15px; font-weight:600; color:var(--navy); margin-bottom:6px; display:flex; align-items:center; gap:8px;}
  .section-desc{font-size:12px; color:var(--muted); margin-bottom:10px;}

  .legend{display:flex; gap:16px; flex-wrap:wrap; font-size:11px; color:var(--muted); margin-bottom:8px;}
  .legend span{display:inline-flex; align-items:center; gap:5px;}
  .swatch{width:11px; height:11px; border-radius:2px; display:inline-block;}

  .scroll-box{overflow-x:auto; overflow-y:hidden; border:1px solid var(--line); border-radius:6px; background:#fff; padding:12px 14px 4px 14px;}

  .tooltip{
    position:fixed; pointer-events:none; background:var(--navy); color:#fff; font-size:12px;
    padding:7px 10px; border-radius:4px; line-height:1.5; box-shadow:0 4px 12px rgba(0,0,0,.25);
    display:none; z-index:50; white-space:nowrap;
  }
  .tooltip b{color:#9FC2F0;}
  .tooltip .ng-tag{color:#FF8A8A; font-weight:600;}

  table{width:100%; border-collapse:collapse; font-size:12.5px;}
  thead th{
    background:var(--navy); color:#fff; text-align:left; padding:8px 10px; position:sticky; top:0;
  }
  tbody td{padding:7px 10px; border-bottom:1px solid var(--line);}
  tbody tr:nth-child(even){background:#FAFBFC;}
  tbody tr:hover{background:#EEF3FA;}
  .table-scroll{max-height:340px; overflow-y:auto; border:1px solid var(--line); border-radius:6px;}
  .dur-badge{
    display:inline-block; padding:2px 7px; border-radius:10px; font-size:11px; font-weight:600;
    background:#FBE7E7; color:var(--red);
  }
  .dur-badge.mid{background:#FCEFDD; color:var(--amber);}
  .ng-pill{
    display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px; font-weight:600;
    background:#FBE7E7; color:var(--red);
  }
  .ok-pill{color:var(--muted); font-size:11px;}

  .axis-label{font-size:10px; fill:var(--muted);}
  .hint{font-size:11px; color:var(--muted); margin-top:6px;}

  .tabs{display:flex; gap:6px; margin-bottom:10px;}
  .tab-btn{
    border:1px solid var(--line); background:#fff; color:var(--muted); font-size:12px;
    padding:6px 14px; border-radius:16px; cursor:pointer;
  }
  .tab-btn.active{background:var(--navy); color:#fff; border-color:var(--navy);}
</style>
</head>
<body>

<h1>__TITLE__</h1>
<div class="subtitle" id="subtitle">数据加载中…</div>

<div class="kpi-row" id="kpiRow"></div>

<div class="section">
  <div class="section-title">① 全天生产节拍总览（按__OVERVIEW_BIN_MIN__分钟分箱）</div>
  <div class="section-desc">柱高 = 该时间段内下线零件数量；颜色反映产出是否连续；红色圆点表示该时段内出现 NG 品</div>
  <div class="legend">
    <span><i class="swatch" style="background:#1F61A8"></i>正常生产</span>
    <span><i class="swatch" style="background:#E08A1E"></i>产出偏低（可能存在小停顿）</span>
    <span><i class="swatch" style="background:#C00000"></i>该时段零产出（疑似停机）</span>
    <span><i class="swatch" style="border-radius:50%;background:#C00000"></i>时段内含 NG 品</span>
  </div>
  <div class="scroll-box" id="chartOverviewBox">
    <svg id="overviewChart"></svg>
  </div>
  <div class="hint">分箱数量较多时图表宽度会变大，请横向滚动查看全部时段</div>
</div>

<div class="section">
  <div class="section-title">② 逐件下线间隔明细 / 累计产量-时间曲线</div>
  <div class="section-desc" id="mode2Desc">__DESC__</div>
  <div class="tabs">
    <button class="tab-btn active" id="btnBar">间隔柱状图</button>
    <button class="tab-btn" id="btnLine">累计产量-时间折线图</button>
  </div>
  <div class="legend" id="legendBar">__LEGEND_BAR__
  </div>
  <div class="legend" id="legendLine" style="display:none;">__LEGEND_LINE__
  </div>
  <div class="scroll-box" id="chartBarBox">
    <svg id="detailChart"></svg>
  </div>
  <div class="scroll-box" id="chartLineBox" style="display:none;">
    <svg id="lineChart"></svg>
  </div>
  <div class="hint">共 <span id="detailCount"></span> 件，图表宽度较大，请横向滚动查看全部记录</div>
</div>

<div class="section">
  <div class="section-title">③ 停机事件清单（间隔 &gt; __STOP_MIN__分钟）</div>
  <div class="section-desc">按停机时长从长到短排列，可用于追溯具体停机原因</div>
  <div class="table-scroll">
    <table>
      <thead>
        <tr><th>#</th><th>停机开始（上一件下线）</th><th>恢复生产（本件下线）</th><th>停机时长</th><th>恢复后首件结果</th></tr>
      </thead>
      <tbody id="stopTableBody"></tbody>
    </table>
  </div>
</div>

<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA_JSON__;

const tooltip = document.getElementById('tooltip');
function showTip(html, x, y){
  tooltip.innerHTML = html;
  tooltip.style.display = 'block';
  const pad = 14;
  let left = x + pad, top = y + pad;
  if(left + 220 > window.innerWidth) left = x - 220;
  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
}
function hideTip(){ tooltip.style.display = 'none'; }

function fmtDT(ts){
  const d = new Date(ts);
  const p = n => String(n).padStart(2,'0');
  return `${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}
function fmtDur(sec){
  if(sec < 60) return sec.toFixed(0)+'s';
  const m = Math.floor(sec/60), s = Math.round(sec%60);
  if(m < 60) return `${m}分${s}秒`;
  const h = Math.floor(m/60), mm = m%60;
  return `${h}时${mm}分`;
}

__CLASSIFY_JS__

// ---------- KPI ----------
const total = DATA.length;
const ngList = DATA.filter(d => d.r === 'NG');
const ngCount = ngList.length;
const okCount = total - ngCount;
const ngRate = (ngCount/total*100).toFixed(1);
const intervals = DATA.map(d=>d.iv).filter(v=>v!==null);
const singleChannel = DATA.filter((d,i)=>CLASSES[i]==='single');
const stops60 = DATA.filter((d,i)=>CLASSES[i]==='stop');
const stops120 = DATA.filter(d=>d.iv!==null && d.iv>1800);
const totalDownSec = stops60.reduce((a,d)=>a+d.iv,0);
const spanMs = DATA[DATA.length-1].ts - DATA[0].ts;
const spanH = (spanMs/3600000);

document.getElementById('subtitle').textContent =
  `数据区间：${fmtDT(DATA[0].ts)} ~ ${fmtDT(DATA[DATA.length-1].ts)}（约 ${spanH.toFixed(1)} 小时，共 ${total} 件记录）`;

const kpis = [
  __KPI_TAKT_CARD__
  __KPI_SHIFT_CARDS__
  {label:'总下线数量', value: total, sub:'件', cls:''},
  {label:'合格 (OK)', value: okCount, sub:`占比 ${(okCount/total*100).toFixed(1)}%`, cls:''},
  {label:'不合格 (NG)', value: ngCount, sub:`NG率 ${ngRate}%`, cls:'ng'},
  __KPI_SINGLE_CARD__
  {label:'停线事件 (>__STOP_MIN__分钟)', value: stops60.length, sub:`其中 >30分钟 ${stops120.length} 次`, cls:'gap'},
  {label:'累计停机时长', value: fmtDur(totalDownSec), sub:`占统计区间 ${(totalDownSec/3600/spanH*100).toFixed(1)}%`, cls:'gap'},
];
document.getElementById('kpiRow').innerHTML = kpis.map(k=>
  `<div class="kpi ${k.cls}"><div class="kpi-label">${k.label}</div><div class="kpi-value">${k.value}</div><div class="kpi-sub">${k.sub}</div></div>`
).join('');

// ---------- Overview chart (__OVERVIEW_BIN_MIN__-min bins) ----------
(function(){
  const BIN_MS = __OVERVIEW_BIN_MS__;
  const start = DATA[0].ts - (DATA[0].ts % BIN_MS);
  const end = DATA[DATA.length-1].ts;
  const nBins = Math.ceil((end-start)/BIN_MS) + 1;
  const bins = new Array(nBins).fill(0).map(()=>({count:0, ng:0}));
  DATA.forEach(d=>{
    const idx = Math.floor((d.ts-start)/BIN_MS);
    if(idx>=0 && idx<nBins){
      bins[idx].count++;
      if(d.r==='NG') bins[idx].ng++;
    }
  });
  const nonZero = bins.map(b=>b.count).filter(c=>c>0);
  nonZero.sort((a,b)=>a-b);
  const median = nonZero[Math.floor(nonZero.length/2)] || 1;

  const W = Math.max(900, nBins*6);
  const H = 150;
  const padL=34, padR=10, padT=10, padB=22;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const barW = plotW/nBins;
  const maxCount = Math.max(...bins.map(b=>b.count), 1);

  const svg = document.getElementById('overviewChart');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.style.display='block';

  let s = '';
  [0,0.5,1].forEach(f=>{
    const y = padT + plotH*(1-f);
    s += `<line x1="${padL}" y1="${y}" x2="${W-padR}" y2="${y}" stroke="#EEF0F3" stroke-width="1"/>`;
    s += `<text x="${padL-6}" y="${y+3}" text-anchor="end" class="axis-label">${Math.round(maxCount*f)}</text>`;
  });

  bins.forEach((b,i)=>{
    const x = padL + i*barW;
    let color;
    if(b.count===0) color='#C00000';
    else if(b.count < median*0.5) color='#E08A1E';
    else color='#1F61A8';
    const h = (b.count/maxCount)*plotH;
    const y = padT + plotH - h;
    const barH = b.count===0 ? 3 : Math.max(h,1.5);
    const barY = b.count===0 ? padT+plotH-3 : y;
    s += `<rect data-i="${i}" x="${x.toFixed(2)}" y="${barY.toFixed(2)}" width="${Math.max(barW-0.6,0.6)}" height="${barH.toFixed(2)}" fill="${color}" opacity="0.92" class="ovbar"/>`;
    if(b.ng>0){
      s += `<circle cx="${(x+barW/2).toFixed(2)}" cy="${padT+3}" r="2.6" fill="#C00000"/>`;
    }
  });
  let lastLabelX = -999;
  bins.forEach((b,i)=>{
    const binStart = start + i*BIN_MS;
    const d = new Date(binStart);
    if(d.getUTCMinutes()===0 || i===0){
      const x = padL + i*barW;
      if(x-lastLabelX > 28){
        s += `<text x="${x.toFixed(2)}" y="${H-6}" class="axis-label" text-anchor="middle">${String(d.getUTCHours()).padStart(2,'0')}:00</text>`;
        s += `<line x1="${x.toFixed(2)}" y1="${padT+plotH}" x2="${x.toFixed(2)}" y2="${padT+plotH+3}" stroke="#B9C0CC"/>`;
        lastLabelX = x;
      }
    }
  });
  svg.innerHTML = s;

  svg.querySelectorAll('.ovbar').forEach(el=>{
    el.addEventListener('mousemove', (e)=>{
      const i = +el.getAttribute('data-i');
      const b = bins[i];
      const binStart = start + i*BIN_MS;
      const ngInfo = b.ng>0 ? `<br><span class="ng-tag">含 ${b.ng} 件 NG</span>` : '';
      showTip(`<b>${fmtDT(binStart)}</b> ~ ${fmtDT(binStart+BIN_MS)}<br>下线数量：${b.count} 件${ngInfo}`, e.clientX, e.clientY);
    });
    el.addEventListener('mouseleave', hideTip);
  });
})();

// ---------- Detail bar chart (per-part interval) ----------
(function(){
  const CAP = STOP_SEC;
  const barW = 5;
  const W = Math.max(900, DATA.length*barW + 40);
  const H = 230;
  const padL=36, padT=14, padB=30;
  const plotH = H - padT - padB;

  const svg = document.getElementById('detailChart');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.style.display='block';

  document.getElementById('detailCount').textContent = DATA.length;

  let s = '';
  const refVal = (TAKT_REF !== null) ? TAKT_REF : SINGLE_MAX;
  const refColor = (TAKT_REF !== null) ? '#1F61A8' : '#C0521E';
  const refLabel = (TAKT_REF !== null) ? `${refVal}s（理论节拍）` : `${refVal}s`;
  const refY_line = padT + plotH - (refVal/CAP)*plotH;
  s += `<line x1="${padL}" y1="${refY_line.toFixed(2)}" x2="${W-10}" y2="${refY_line.toFixed(2)}" stroke="${refColor}" stroke-dasharray="4,3" stroke-width="1"/>`;
  s += `<text x="4" y="${refY_line+3}" class="axis-label" fill="${refColor}">${refLabel}</text>`;

  [100,200,300].forEach(v=>{
    const y = padT + plotH - (v/CAP)*plotH;
    const lbl = v>=60 ? `${Math.round(v/60)}分` : `${v}s`;
    s += `<text x="6" y="${y+3}" class="axis-label">${lbl}</text>`;
    s += `<line x1="${padL}" y1="${y.toFixed(2)}" x2="${W-10}" y2="${y.toFixed(2)}" stroke="#F2F3F5" stroke-width="1"/>`;
  });

  DATA.forEach((d,i)=>{
    const x = padL + i*barW;
    if(d.iv===null) return;
    const iv = d.iv;
    const color = CLASS_COLOR[CLASSES[i]];
    const clipped = iv > CAP;
    const hVal = Math.min(iv, CAP);
    const h = (hVal/CAP)*plotH;
    const y = padT + plotH - h;
    s += `<rect data-i="${i}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barW-1}" height="${Math.max(h,1)}" fill="${color}" opacity="0.9" class="dbar"/>`;
    if(clipped){
      s += `<polygon points="${(x+(barW-1)/2).toFixed(2)},${padT-3} ${(x).toFixed(2)},${padT+4} ${(x+barW-1).toFixed(2)},${padT+4}" fill="#C00000"/>`;
    }
    if(d.r==='NG'){
      s += `<circle data-i="${i}" cx="${(x+(barW-1)/2).toFixed(2)}" cy="${padT+plotH+14}" r="2.8" fill="#C00000" class="ngdot"/>`;
    }
  });

  let lastLabelX = -999;
  DATA.forEach((d,i)=>{
    const dt = new Date(d.ts);
    if(dt.getUTCMinutes()===0 && dt.getUTCSeconds()<30){
      const x = padL + i*barW;
      if(x-lastLabelX>50){
        s += `<text x="${x.toFixed(2)}" y="${H-6}" class="axis-label" text-anchor="middle">${String(dt.getUTCHours()).padStart(2,'0')}:00</text>`;
        lastLabelX = x;
      }
    }
  });

  svg.innerHTML = s;

  svg.querySelectorAll('.dbar,.ngdot').forEach(el=>{
    el.addEventListener('mousemove', (e)=>{
      const i = +el.getAttribute('data-i');
      const d = DATA[i];
      const ngTag = d.r==='NG' ? `<br><span class="ng-tag">该件为 NG</span>` : '';
      const clsLabel = {dual:'双通道正常', single:'单通道异常生产', pause:'异常停顿', stop:'停线'}[CLASSES[i]] || '';
      showTip(`<b>${fmtDT(d.ts)}</b><br>与上件间隔：${d.iv.toFixed(1)}s（${clsLabel}）${ngTag}`, e.clientX, e.clientY);
    });
    el.addEventListener('mouseleave', hideTip);
  });
})();

// ---------- Line chart: X=累计生产数量(分度值1), Y=时间 ----------
(function(){
  const n = DATA.length;
  const stepX = 5;
  const padL = 74, padR = 20, padT = 16, padB = 34;
  const W = padL + padR + n*stepX;
  const H = 620;
  const plotH = H - padT - padB;

  const t0 = DATA[0].ts, t1 = DATA[n-1].ts;
  const yScale = (ts) => padT + (ts - t0) / (t1 - t0) * plotH;

  const svg = document.getElementById('lineChart');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.style.display = 'block';

  let s = '';

  const HALF_HOUR = 30*60*1000;
  let ty = t0 - (t0 % HALF_HOUR);
  while(ty <= t1){
    if(ty >= t0){
      const y = yScale(ty);
      const d = new Date(ty);
      const p = nn => String(nn).padStart(2,'0');
      s += `<line x1="${padL}" y1="${y.toFixed(2)}" x2="${W-padR}" y2="${y.toFixed(2)}" stroke="#EEF0F3" stroke-width="1"/>`;
      s += `<text x="${padL-8}" y="${y.toFixed(2)+3}" text-anchor="end" class="axis-label">${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}</text>`;
    }
    ty += HALF_HOUR;
  }

  for(let i=0;i<n;i++){
    const x = padL + i*stepX;
    if(i % 10 === 0){
      s += `<line x1="${x.toFixed(2)}" y1="${padT+plotH}" x2="${x.toFixed(2)}" y2="${padT+plotH+3}" stroke="#D9DEE5" stroke-width="1"/>`;
    }
    if(i % 50 === 0){
      s += `<text x="${x.toFixed(2)}" y="${H-14}" class="axis-label" text-anchor="middle">${i}</text>`;
      s += `<line x1="${x.toFixed(2)}" y1="${padT+plotH}" x2="${x.toFixed(2)}" y2="${padT+plotH+6}" stroke="#B9C0CC" stroke-width="1"/>`;
    }
  }
  s += `<text x="${padL+n*stepX/2}" y="${H-2}" class="axis-label" text-anchor="middle" style="font-size:11px;">累计生产数量（件，分度值=1）</text>`;
__TAKT_REF_JS__
  for(let i=1;i<n;i++){
    const iv = DATA[i].iv;
    const x0 = padL + (i-1)*stepX, y0 = yScale(DATA[i-1].ts);
    const x1 = padL + i*stepX, y1 = yScale(DATA[i].ts);
    const color = CLASS_COLOR[CLASSES[i]];
    const strokeW = iv>STOP_SEC ? 2.2 : 1.4;
    s += `<line data-i="${i}" x1="${x0.toFixed(2)}" y1="${y0.toFixed(2)}" x2="${x1.toFixed(2)}" y2="${y1.toFixed(2)}" stroke="${color}" stroke-width="${strokeW}" class="lseg"/>`;
  }

  for(let i=0;i<n;i++){
    const x = padL + i*stepX;
    const y = yScale(DATA[i].ts);
    const isNG = DATA[i].r === 'NG';
    const r = isNG ? 3.2 : 1.6;
    const fill = isNG ? '#C00000' : '#1F61A8';
    s += `<circle data-i="${i}" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${r}" fill="${fill}" class="lpt" ${isNG?'opacity="0.95"':'opacity="0.7"'}/>`;
  }

  svg.innerHTML = s;

  svg.querySelectorAll('.lseg,.lpt').forEach(el=>{
    el.addEventListener('mousemove', (e)=>{
      const i = +el.getAttribute('data-i');
      const d = DATA[i];
      const ivTxt = d.iv!==null ? `${d.iv.toFixed(1)}s` : '—';
      const clsLabel = CLASSES[i] ? ({dual:'双通道正常', single:'单通道异常生产', pause:'异常停顿', stop:'停线'}[CLASSES[i]]||'') : '';
      const clsTxt = clsLabel ? `（${clsLabel}）` : '';
      const ngTag = d.r==='NG' ? `<br><span class="ng-tag">该件为 NG</span>` : '';
      showTip(`<b>第 ${i+1} 件</b><br>时间：${fmtDT(d.ts)}<br>与上件间隔：${ivTxt}${clsTxt}${ngTag}`, e.clientX, e.clientY);
    });
    el.addEventListener('mouseleave', hideTip);
  });
})();

document.getElementById('btnBar').addEventListener('click', ()=>{
  document.getElementById('btnBar').classList.add('active');
  document.getElementById('btnLine').classList.remove('active');
  document.getElementById('chartBarBox').style.display = '';
  document.getElementById('chartLineBox').style.display = 'none';
  document.getElementById('legendBar').style.display = '';
  document.getElementById('legendLine').style.display = 'none';
});
document.getElementById('btnLine').addEventListener('click', ()=>{
  document.getElementById('btnLine').classList.add('active');
  document.getElementById('btnBar').classList.remove('active');
  document.getElementById('chartLineBox').style.display = '';
  document.getElementById('chartBarBox').style.display = 'none';
  document.getElementById('legendLine').style.display = '';
  document.getElementById('legendBar').style.display = 'none';
});

// ---------- Stoppage table ----------
(function(){
  const stops = [];
  for(let i=1;i<DATA.length;i++){
    const d = DATA[i];
    if(d.iv!==null && d.iv>STOP_SEC){
      stops.push({ prevTs: DATA[i-1].ts, curTs: d.ts, dur: d.iv, result: d.r });
    }
  }
  stops.sort((a,b)=>b.dur-a.dur);
  const rows = stops.map((s,idx)=>{
    const badgeCls = s.dur>1800 ? '' : 'mid';
    const resultHtml = s.result==='NG' ? `<span class="ng-pill">NG</span>` : `<span class="ok-pill">OK</span>`;
    return `<tr>
      <td>${idx+1}</td>
      <td>${fmtDT(s.prevTs)}</td>
      <td>${fmtDT(s.curTs)}</td>
      <td><span class="dur-badge ${badgeCls}">${fmtDur(s.dur)}</span></td>
      <td>${resultHtml}</td>
    </tr>`;
  }).join('');
  document.getElementById('stopTableBody').innerHTML = rows || '<tr><td colspan="5">无超过__STOP_MIN__分钟的停线事件</td></tr>';
})();
</script>
</body>
</html>
"""

    html = html.replace("__TITLE__", title)
    html = html.replace("__DESC__", desc)
    html = html.replace("__LEGEND_BAR__", legend_bar)
    html = html.replace("__LEGEND_LINE__", legend_line)
    html = html.replace("__STOP_MIN__", f"{stop_sec/60:g}")
    html = html.replace("__OVERVIEW_BIN_MIN__", f"{args.overview_bin_min:g}")
    html = html.replace("__OVERVIEW_BIN_MS__", f"{int(args.overview_bin_min*60*1000)}")
    html = html.replace("__KPI_SINGLE_CARD__", kpi_single_card)
    html = html.replace("__KPI_TAKT_CARD__", kpi_takt_card)
    html = html.replace("__KPI_SHIFT_CARDS__", kpi_shift_cards)
    html = html.replace("__CLASSIFY_JS__", classify_js)
    html = html.replace("__TAKT_REF_JS__", takt_ref_js)
    html = html.replace("__DATA_JSON__", data_json)

    with open(args.out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[完成] 已写出 {args.out_html} ({len(html)/1024:.1f} KB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-json", required=True)
    ap.add_argument("--out-html", required=True)
    ap.add_argument("--title", default="线体生产连续性分析")
    ap.add_argument("--mode", choices=["dual", "single"], default="dual")
    ap.add_argument("--pair-sum-max", type=float, default=40,
                     help="[dual模式] 相邻两件间隔之和小于此值 -> 双通道正常")
    ap.add_argument("--single-max", type=float, default=45,
                     help="[dual模式] 单通道异常生产的上限；[single模式] 正常生产的上限")
    ap.add_argument("--stop-sec", type=float, default=300, help="超过此秒数记为停线")
    ap.add_argument("--takt", type=float, default=None,
                     help="理论节拍（秒），用于折线图的灰色参考线，可选")
    ap.add_argument("--overview-bin-min", type=float, default=30,
                     help="①全天生产总览图的分箱间隔（分钟），默认30分钟")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
