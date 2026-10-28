# Takt-time discovery methodology

This documents the reasoning behind `scripts/analyze_interval.py`'s takt-time
logic, distilled from an interactive analysis session on a real dual-channel
NEV drive-motor stator/rotor line.

## The core idea

The person's framing (verified against real data, works well):

> 生产间隔如果规律、稳定且平均最短，即为连续生产模式，这一段的平均间隔就是
> 生产节拍。
>
> If the production interval is regular, stable, AND averages the shortest,
> that's the continuous-production mode — the average interval of that
> segment is the takt time.

This is deliberately different from just taking the global minimum interval
(too noisy / could be a data glitch) or the global mean (dragged up by
pauses and degraded-mode periods). It's also different from the mode
(most frequent single value) when the line has a bimodal short/long
alternation pattern — see below.

## Implementation: rolling-window scan

For several window sizes (15/20/30/50 consecutive parts):
1. Compute rolling mean and rolling std over the interval series.
2. Compute CV = std/mean (coefficient of variation) — low CV means "regular
   and stable" within that window.
3. Exclude windows whose max value exceeds a "likely contains a pause"
   guess (default 60s) — a single stoppage inside an otherwise-tight window
   would still register as containing a huge spike, but excluding by max
   (not just by CV) catches short windows where the spike doesn't move the
   mean/CV much.
4. Among the remaining (stable, pause-free) windows, take the one with the
   lowest mean — this is "the fastest stretch that's also consistent," i.e.
   continuous production, not a fluke single fast cycle.

Do this across multiple window sizes and check whether they agree (relative
spread of the resulting means). Convergence across window sizes is strong
evidence the number is real, not an artifact of one particular window
choice. In validation:

| window | best-segment mean | cv |
|---|---|---|
| 15 | 16.53s | 0.248 |
| 20 | 16.55s | 0.236 |
| 30 | 16.67s | 0.239 |
| 50 | 16.78s | 0.240 |

(<2% spread — highly convergent → 16.5–16.8s accepted as the takt.)

**Tuning note**: `cv_max=0.25` and `pause_guess=60` were what produced this
convergence. Tighter thresholds (`cv_max=0.15`, `pause_guess=45`) caused
different window sizes to lock onto *different* stable segments (one found
the ~16.7s dual-channel-interleaved segment, another found a ~30s
single-channel-only segment that happened to be very locally consistent).
If you see non-convergent results, don't just report the minimum — go look
at the interval distribution (percentiles + top value counts) to understand
what's actually happening before picking a number.

## Cross-validation against classification

As a sanity check, the discovered takt should roughly match the mean/median
of whatever subset of intervals gets classified as "normal" by the
dual/single-channel classifier (see SKILL.md Step 3-4). On the validated
line: rolling-window takt ≈ 16.7s; mean of all "dual-normal"-classified
intervals (using the pair-sum<40 rule) = 16.3s, median = 16.0s. Close
agreement between two independently-derived numbers is good evidence both
are capturing something real.

## Why dual-channel lines show a bimodal interval distribution

A shared dual-channel line (two stations/heads feeding one discharge port,
interleaved) produces two distinguishable patterns depending on how evenly
phase-balanced the two channels are:

- **Well-balanced** (channels evenly offset in phase): the combined output
  stream has fairly uniform spacing ≈ half of each channel's own cycle
  time. This is what the rolling-window scan finds as "the theoretical
  takt" — e.g. 16.5–17s when each channel's own cycle is ~33–34s.
- **Poorly-balanced / one channel lagging**: the combined stream alternates
  a short gap (immediately after the other channel fires) with a long gap
  (waiting for the slower channel) — e.g. an observed 8-9s cluster paired
  with a 23-34s cluster, summing to roughly the same ~33-35s combined
  cycle. This is normal — just less evenly interleaved — and should still
  classify as "dual-channel normal," which is why the classifier tests
  **pairwise sums** (adjacent-interval sum < threshold) rather than
  requiring each individual interval to be near the takt.

If one channel actually drops out entirely, every interval flattens to
~1x the single channel's own cycle time (no more short/long alternation,
and no pair sums below the threshold) — that's the "single-channel
degraded" tier.

## Classification thresholds used on the validated line

These are the specific numbers that worked for the one line fully validated
so far — **starting points to re-derive, not universal constants**:

- Takt (per combined-output part): ~17s
- Pair-sum threshold for "dual-channel normal": 40s (channel's own full
  cycle is ~33-34s; two normal adjacent intervals summing under ~40s
  reliably indicates interleaving, since the >40s case only shows up once
  interleaving has broken down)
- Single-channel-degraded upper bound: 45s (a bit above the ~35s
  single-channel cycle to leave margin for jitter, but low enough not to
  overlap with genuine pauses)
- Abnormal-pause range: 45s – 5 minutes
- Line-stop threshold: > 5 minutes (this was a business-supplied number
  from the user, not derived from the data — always confirm the stop
  threshold with the user rather than assuming 5 minutes generalizes)
