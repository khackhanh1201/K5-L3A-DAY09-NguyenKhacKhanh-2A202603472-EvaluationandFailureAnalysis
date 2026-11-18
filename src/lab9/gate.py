"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for who, rep in (("PR", pr), ("baseline", base)):
        problems += [f"{who}: {p}" for p in _report_problems(rep, graded)]
    # The PR must cover exactly the baseline's (item, seed) trials, with the same slice tags.
    pr_keys, base_keys = _keys(pr), _keys(base)
    missing, extra = base_keys - pr_keys, pr_keys - base_keys
    if missing:
        problems.append(f"PR lacks {len(missing)} (item, seed) trial(s) the baseline has, e.g. "
                        f"{_fmt(sorted(missing)[:3])} (dropped rows or cherry-picked seeds/items)")
    if extra:
        problems.append(f"PR has {len(extra)} (item, seed) trial(s) the baseline lacks, e.g. {_fmt(sorted(extra)[:3])}")
    pm, bm = pr.get("manifest", {}), base.get("manifest", {})
    if sorted(pm.get("seeds") or []) != sorted(bm.get("seeds") or []) or pm.get("items") != bm.get("items"):
        problems.append(f"manifest differs from the baseline's: items {pm.get('items')} vs {bm.get('items')}, "
                        f"seeds {pm.get('seeds')} vs {bm.get('seeds')}")
    pr_tags, base_tags = _slice_tags(pr), _slice_tags(base)
    for item in sorted(set(pr_tags) & set(base_tags)):
        if pr_tags[item] != base_tags[item]:
            problems.append(f"{item}: slice tags {sorted(pr_tags[item])} differ from the baseline's "
                            f"{sorted(base_tags[item])} (relabelled out of a slice)")
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _keys(rep: dict) -> set[tuple[str, int]]:
    return {(r.get("item_id"), r.get("seed")) for r in rep.get("rows", [])}


def _fmt(keys: list[tuple[str, int]]) -> str:
    return ", ".join(f"{i}@{s}" for i, s in keys)


def _slice_tags(rep: dict) -> dict[str, frozenset]:
    """item -> slice tags; an item whose rows disagree with each other gets a marker that never matches."""
    tags: dict[str, set] = {}
    for r in rep.get("rows", []):
        t = frozenset(r.get("slices") or [])
        tags.setdefault(r.get("item_id"), set()).add(t)
    return {i: (next(iter(ts)) if len(ts) == 1 else frozenset({"<inconsistent>"})) for i, ts in tags.items()}


def _bad_number(v) -> bool:
    return isinstance(v, float) and not math.isfinite(v)


def _report_problems(rep: dict, graded: list[str]) -> list[str]:
    """Problems inside one report: it must be a complete, self-consistent output of lab9.eval."""
    out = []
    metrics, rows, man = rep.get("metrics") or {}, rep.get("rows") or [], rep.get("manifest") or {}
    out += [f"metric {k} is {v} (NaN/inf)" for k, v in metrics.items() if _bad_number(v)]
    if rep.get("evaluator_failures"):
        out.append(f"{len(rep['evaluator_failures'])} evaluator failure(s), first: {rep['evaluator_failures'][0]}")
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        out.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = len(keys) - len(set(keys))
    if dup:
        out.append(f"{dup} duplicated (item, seed) row(s)")
    seeds = set(man.get("seeds") or [])
    if seeds and any(r.get("seed") not in seeds for r in rows):
        out.append("rows carry seeds outside the manifest")
    for m in graded:
        if any(m in r for r in rows):
            vals = [r.get(m) for r in rows]
            none = sum(v is None for v in vals)
            if none:
                out.append(f"{none} row(s) have no value for graded metric {m} (crashed grader dropped from the mean)")
            if any(_bad_number(v) for v in vals):
                out.append(f"rows hold NaN/inf for {m}")
            # The summary must be what the rows say: a hand-edited metric is not evidence.
            ok = [v for v in vals if v is not None and not _bad_number(v)]
            if ok and isinstance(metrics.get(m), (int, float)) and not _bad_number(metrics[m]):
                recomputed = sum(ok) if m in SAFETY_COUNTS else round(sum(ok) / len(ok), 4)
                if abs(recomputed - metrics[m]) > 1e-9:
                    out.append(f"metric {m}={metrics[m]} does not match its rows ({recomputed})")
    out += _passk_problems(metrics, rows)
    return out


def _passk_problems(metrics: dict, rows: list[dict]) -> list[str]:
    """pass_5 / pass_at_k / pass_hat_k are derived from the per-row pass_rate: recompute them too."""
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        if "pass_rate" in r and r["pass_rate"] is not None:
            by_item.setdefault(r["item_id"], []).append(bool(r["pass_rate"]))
    if not by_item:
        return []
    want: dict[str, float] = {"pass_5": round(sum(all(v) for v in by_item.values()) / len(by_item), 4)}
    for key in metrics:
        name, _, k = key.rpartition("_")
        if name in ("pass_at", "pass_hat") and k.isdigit() and min(map(len, by_item.values())) >= int(k):
            fn = stats.pass_at_k if name == "pass_at" else stats.pass_hat_k
            est = [fn(len(v), sum(v), int(k)) for v in by_item.values()]
            want[key] = round(sum(est) / len(est), 4)
    return [f"metric {k}={metrics[k]} does not match its rows ({v})" for k, v in want.items()
            if isinstance(metrics.get(k), (int, float)) and not _bad_number(metrics[k]) and abs(metrics[k] - v) > 1e-9]


SAFETY_COUNTS = {"secret_leak", "approval_bypass"}   # lab9.eval.aggregate sums these, averages the rest


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version => thresholds may only get stricter. A new eval-set version starts over."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    out = []
    new = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        if m["id"] not in new:
            out.append(f"ratchet: metric {m['id']} was removed from the spec")
            continue
        out += _looser(f"metric {m['id']}", m, m.get("threshold") or {}, new[m["id"]], new[m["id"]].get("threshold") or {})
    new_sl = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s.get("name"), s.get("metric"))
        if key not in new_sl:
            out.append(f"ratchet: slice {key[0]}/{key[1]} was removed from the spec")
            continue
        out += _looser(f"slice {key[0]}/{key[1]}", s, s, new_sl[key], new_sl[key])
    bs, nb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    for k in ("rng", "method"):
        if k in bs and nb.get(k) != bs[k]:
            out.append(f"ratchet: bootstrap {k} changed {bs[k]!r} -> {nb.get(k)!r} (re-rolling the CI)")
    if "confidence" in bs and (nb.get("confidence") or 0) > bs["confidence"]:
        out.append(f"ratchet: bootstrap confidence raised {bs['confidence']} -> {nb.get('confidence')} (wider CI blocks less)")
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        out.append(f"ratchet: seeds changed {base_spec.get('seeds')} -> {spec.get('seeds')}")
    return out


def _looser(what: str, old: dict, old_th: dict, new: dict, new_th: dict) -> list[str]:
    out = []
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"ratchet: {what} is no longer blocking")
    for k in ("max", "max_increase"):
        if k in old_th and (k not in new_th or new_th[k] > old_th[k]):
            out.append(f"ratchet: {what} {k} {old_th[k]} -> {new_th.get(k, 'removed')}")
    if "min" in old_th and ("min" not in new_th or new_th["min"] < old_th["min"]):
        out.append(f"ratchet: {what} min {old_th['min']} -> {new_th.get('min', 'removed')}")
    if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
        out.append(f"ratchet: {what} dropped no_significant_drop")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", f"{len(a)} item(s)"
        if val is None:
            verdict = "missing"                       # an empty slice proves nothing: do not pass it
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        if s.get("no_significant_drop") and a:
            b = per_item(base, metric, slice_name=name)
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note += f" Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
