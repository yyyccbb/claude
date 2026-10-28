#!/usr/bin/env python3
"""
analyze_interval.py — Parse a production-log CSV and discover the line's
theoretical takt time (节拍), plus print diagnostics to help decide whether
the line is a shared dual-channel setup or a plain single-channel line.

Usage:
    python analyze_interval.py --csv "历史记录.csv" [--time-col 时间] \
        [--result-col 测试总结果] [--out-json data.json] [--stop-sec 300]

Output:
    - Writes <out-json> with records: [{"ts": epoch_ms, "iv": seconds|null, "r": "OK"|"NG"}, ...]
      sorted chronologically. epoch_ms is derived from the naive timestamp
      AS-IS (no timezone conversion) — see the "timezone gotcha" note in
      SKILL.md before rendering this in a browser.
    - Prints a diagnostic report to stdout: interval percentiles, most
      frequent interval values (rounded), and a rolling-window scan that
      finds the most stable + fastest segment (candidate takt time).

This script makes NO decision about dual-channel vs single-channel — it only
surfaces evidence. Read the printed report and decide:
    - Bimodal distribution (a short cluster + a long cluster whose typical
      sum ≈ 2x the candidate takt) → likely a shared dual-channel line.
      Use build_dashboard.py --mode dual --pair-sum-max <short+long boundary>.
    - Single tight cluster near the candidate takt → single-channel line.
      Use build_dashboard.py --mode single --normal-max <takt * ~1.3>.
"""
import argparse
import json
import sys
from collections import Counter

import numpy as np
import pandas as pd


def parse_time_column(series):
    """Try a few common formats seen in these production logs before
    falling back to pandas' generic (slower) parser."""
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = pd.to_datetime(series, format=fmt, errors="raise")
            return parsed
        except (ValueError, TypeError):
            continue
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        n_bad = int(parsed.isna().sum())
        print(f"[警告] 时间列有 {n_bad} 行无法解析，请检查原始数据/格式", file=sys.stderr)
    return parsed


def rolling_takt_scan(ivs: pd.Series, windows=(15, 20, 30, 50), cv_max=0.25,
                       pause_guess=60):
    """Scan multiple rolling-window sizes; within windows that don't contain
    a likely pause/stoppage (max < pause_guess) and are internally stable
    (cv < cv_max), find the one with the lowest mean. That's the candidate
    theoretical takt — the most regular, stable, fastest segment."""
    results = []
    for window in windows:
        roll_mean = ivs.rolling(window).mean()
        roll_std = ivs.rolling(window).std()
        cv = roll_std / roll_mean
        roll_max = ivs.rolling(window).max()
        mask = (roll_max < pause_guess) & (cv < cv_max)
        sub = roll_mean[mask]
        if len(sub) == 0:
            continue
        idxmin = sub.idxmin()
        results.append({
            "window": window,
            "mean": float(roll_mean[idxmin]),
            "cv": float(cv[idxmin]),
            "end_index": int(idxmin),
        })
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--time-col", default="时间")
    ap.add_argument("--result-col", default="测试总结果")
    ap.add_argument("--out-json", default="data.json")
    ap.add_argument("--stop-sec", type=float, default=300,
                     help="间隔超过此秒数记为停线（默认5分钟）")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    if args.time_col not in df.columns or args.result_col not in df.columns:
        print(f"[错误] CSV 列名不匹配。实际列名: {list(df.columns)}", file=sys.stderr)
        print(f"       期望的时间列: '{args.time_col}'，结果列: '{args.result_col}'", file=sys.stderr)
        print("       请用 --time-col / --result-col 指定实际列名", file=sys.stderr)
        sys.exit(1)

    df = df[[args.time_col, args.result_col]].copy()
    df.columns = ["时间", "结果"]
    df["时间"] = parse_time_column(df["时间"])
    df = df.dropna(subset=["时间"]).sort_values("时间").reset_index(drop=True)
    df["间隔"] = df["时间"].diff().dt.total_seconds()

    n = len(df)
    ok_count = int((df["结果"] == "OK").sum())
    ng_count = n - ok_count
    span_h = (df["时间"].iloc[-1] - df["时间"].iloc[0]).total_seconds() / 3600

    print("=" * 60)
    print(f"记录数: {n}  (OK {ok_count} / NG {ng_count}, NG率 {ng_count/n*100:.1f}%)")
    print(f"时间范围: {df['时间'].iloc[0]} ~ {df['时间'].iloc[-1]}  (约 {span_h:.1f} 小时)")
    print("=" * 60)

    ivs = df["间隔"]
    valid = ivs.dropna()

    print("\n[间隔分布 - 百分位数]")
    for p in (10, 25, 50, 75, 90, 95, 99):
        print(f"  P{p:>2}: {np.percentile(valid, p):.1f}s")

    print("\n[最常见间隔取值 - 四舍五入到整数秒，仅看 <=90s 的] (可能揭示双通道的短/长两簇)")
    pool = valid[valid <= 90].round().astype(int)
    counter = Counter(pool)
    for v, cnt in counter.most_common(15):
        print(f"  {v:>3}s : {cnt} 次")

    print(f"\n[停线粗筛] 间隔 > {args.stop_sec:.0f}s 的次数: {int((valid > args.stop_sec).sum())}")

    print("\n[滚动窗口稳定段扫描 -> 理论节拍候选]")
    scan = rolling_takt_scan(ivs)
    if not scan:
        print("  未找到足够稳定的窗口（可尝试放宽 cv_max 或检查数据是否含大量停顿）")
    else:
        for r in scan:
            print(f"  window={r['window']:>3}件  最优段均值={r['mean']:.2f}s  cv={r['cv']:.3f}  (结束于第{r['end_index']}行)")
        means = [r["mean"] for r in scan]
        best = min(scan, key=lambda r: r["mean"])
        spread = (max(means) - min(means)) / min(means)
        print(f"\n  >>> 建议理论节拍 ≈ {best['mean']:.1f}s "
              f"(来自 window={best['window']} 的最稳定+最快分段，cv={best['cv']:.3f})")
        if spread < 0.15:
            print(f"      各窗口大小结果高度一致（相对差异 {spread*100:.0f}%），该节拍数字可信。")
        else:
            print(f"      [注意] 各窗口大小结果分散（相对差异 {spread*100:.0f}%），"
                  "说明可能存在双通道交替、或数据中有多个稳定工况段，"
                  "请结合上面的间隔分布（是否双峰）人工判断，不要直接采用单一数字。")

    records = []
    for _, row in df.iterrows():
        iv = row["间隔"]
        records.append({
            "ts": int(row["时间"].timestamp() * 1000),
            "iv": None if pd.isna(iv) else round(float(iv), 1),
            "r": row["结果"],
        })
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"\n[完成] 已写出 {args.out_json}（{len(records)} 条记录）")


if __name__ == "__main__":
    main()
