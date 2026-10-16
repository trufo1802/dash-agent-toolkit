"""Inventory plotting calls in a notebook -> kwarg coverage checklist for the twin.

Why: when a notebook plots through a project helper (fv.plot_df_subplots(...)),
the one-line cell is NOT the spec - the helper's 300 lines are. The port must
honor every kwarg the notebook actually passes (axis tags, threshold_fill,
title_last_yymmdd, ...). This lists them so "supported" is checkable, and so
an unsupported kwarg becomes a deliberate NotImplementedError, never a silent
drop.

Usage:
    python plot_calls.py cta.ipynb [--receiver fv] [--prefix plot_ --prefix color_table] [--json out.json]

Default receivers: any. Default prefixes catch helper calls (plot_*, color_table,
heatmap) AND inline matplotlib/pandas plotting (ax.plot, plt.bar, df.plot,
fill_between, twinx, annotate) so the archetype (helper-driven vs inline) is
visible from the receiver column.

Output: one markdown table (function | calls | cells | kwargs used | max positional),
then per function each kwarg with example literal values. ASCII only (cp949 consoles).
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_PREFIXES = ("plot", "color_table", "heatmap", "imshow", "bar", "hist", "scatter",
                    "fill_between", "twinx", "axhline", "axvline", "annotate", "style", "subplots")


def _strip_magics(src: str) -> str:
    return "\n".join("" if re.match(r"^\s*[%!]", ln) else ln for ln in src.splitlines())


def _recv(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _recv(node.value) + "." + node.attr
    if isinstance(node, ast.Call):
        return _recv(node.func) + "()"
    if isinstance(node, ast.Subscript):
        return _recv(node.value) + "[]"
    return type(node).__name__


def inventory(nb_path: str, receivers: list[str] | None, prefixes: tuple[str, ...]) -> dict:
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    calls: dict[str, dict] = defaultdict(lambda: {"cells": set(), "kwargs": defaultdict(set),
                                                   "max_pos": 0, "star_kwargs_cells": set(), "n": 0})
    skipped = []
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = _strip_magics("".join(cell.get("source", [])))
        try:
            tree = ast.parse(src)
        except SyntaxError:
            skipped.append(i)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute):
                name, recv = f.attr, _recv(f.value)
            elif isinstance(f, ast.Name):
                name, recv = f.id, ""
            else:
                continue
            if receivers and recv.split(".")[0] not in receivers:
                continue
            if not any(name.startswith(p) for p in prefixes):
                continue
            key = f"{recv}.{name}" if recv else name
            rec = calls[key]
            rec["n"] += 1
            rec["cells"].add(i)
            rec["max_pos"] = max(rec["max_pos"], len(node.args))
            for kw in node.keywords:
                if kw.arg is None:
                    rec["star_kwargs_cells"].add(i)
                    continue
                seg = ast.get_source_segment(src, kw.value) or "?"
                seg = re.sub(r"\s+", " ", seg)
                rec["kwargs"][kw.arg].add(seg[:40] + ("..." if len(seg) > 40 else ""))
    out = {"notebook": nb_path, "skipped_cells": skipped, "calls": {}}
    for key, rec in sorted(calls.items(), key=lambda kv: -kv[1]["n"]):
        out["calls"][key] = {"n": rec["n"], "cells": sorted(rec["cells"]), "max_pos": rec["max_pos"],
                             "kwargs": {k: sorted(v) for k, v in sorted(rec["kwargs"].items())},
                             "star_kwargs_cells": sorted(rec["star_kwargs_cells"])}
    return out


def render(inv: dict) -> str:
    lines = [f"# plot calls in {inv['notebook']}", "",
             "| function | calls | cells | kwargs used | max positional |", "|---|---|---|---|---|"]
    for key, rec in inv["calls"].items():
        cells = ",".join(map(str, rec["cells"][:12])) + ("..." if len(rec["cells"]) > 12 else "")
        lines.append(f"| `{key}` | {rec['n']} | {cells} | {', '.join(rec['kwargs']) or '-'} | {rec['max_pos']} |")
    lines.append("")
    for key, rec in inv["calls"].items():
        if not rec["kwargs"] and not rec["star_kwargs_cells"]:
            continue
        lines.append(f"## `{key}`")
        for k, vals in rec["kwargs"].items():
            lines.append(f"- `{k}` = " + " | ".join(f"`{v}`" for v in vals[:4]))
        if rec["star_kwargs_cells"]:
            lines.append(f"- **`**kwargs` splat in cells {rec['star_kwargs_cells']} - read those by hand; "
                         f"the static list above is incomplete there**")
        lines.append("")
    if inv["skipped_cells"]:
        lines.append(f"skipped (unparseable) cells: {inv['skipped_cells']}")
    helpers = [k for k in inv["calls"] if not k.split(".")[0] in ("ax", "plt", "axes", "fig", "sns", "df", "")]
    lines.append("")
    lines.append("Twin rule: every kwarg above must be accepted by the Plotly twin of its helper; "
                 "unsupported -> raise NotImplementedError(kwarg), never ignore. "
                 f"Helper-receiver calls (port the HELPER, not the cell): {len(helpers)}.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notebook")
    ap.add_argument("--receiver", action="append", help="only calls on this alias (e.g. fv); repeatable")
    ap.add_argument("--prefix", action="append", help="function-name prefix filter; repeatable")
    ap.add_argument("--json", help="also write the inventory as JSON")
    a = ap.parse_args()
    inv = inventory(a.notebook, a.receiver, tuple(a.prefix) if a.prefix else DEFAULT_PREFIXES)
    if a.json:
        Path(a.json).write_text(json.dumps(inv, indent=1), encoding="utf-8")
    print(render(inv))


if __name__ == "__main__":
    main()
