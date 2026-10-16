"""Structural figure spec + diff: matplotlib Figure vs Plotly Figure.

Why: numeric parity proves the ARRAYS match; nothing proves the FIGURE does.
A port that drops a secondary axis, a threshold fill, per-point colors, or a
two-line title renders without error and passes every numeric test. This
module reduces both figures to the same small dict (panels -> sides -> marks)
so a visual mismatch becomes a failing assertion with a readable message
instead of a screenshot someone has to eyeball, one defect per round-trip.

Usage (pytest, see test_visual_parity.py):
    from fig_spec import capture_mpl, mpl_spec, plotly_spec, diff_spec
    figs   = capture_mpl(fv.plot_df_subplots, dfs, axis=[...], threshold_fill=[...])
    golden = mpl_spec(figs[0])                                   # NOTEBOOK helper
    got    = plotly_spec(fv_plotly.plot_df_subplots(dfs, axis=[...], threshold_fill=[...]))
    errs   = [m for m in diff_spec(golden, got) if m.startswith("ERR")]
    assert not errs, "\\n".join(errs)

CLI:
    python fig_spec.py diff golden.json port.json        # two saved specs
    python fig_spec.py sheet mpl.png plotly.png out.png  # side-by-side contact sheet

Spec shape (identical from both extractors):
    suptitle, grid=[nrows, ncols], panels=[{
        index, row, col, title_lines, xlabel, ylabel, ylabel_right, yscale,
        n_secondary, ylim,
        lines/fills/markers: {"left": [...], "right": [...]},
        scatter_n_points, scatter_n_colors, hlines, vlines, texts, legend, bars}]
Colors are '#rrggbb' (alpha dropped); transparent -> None.
Requires matplotlib (for color parsing) even on the plotly side; PIL for sheets.
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

_PLOTLY_COLORWAY = ["#636efa", "#EF553B", "#00cc96", "#ab63fa", "#FFA15A",
                    "#19d3f3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"]


# ---------------------------------------------------------------- helpers ---
def _hex(c: Any) -> str | None:
    """Any mpl/plotly color -> '#rrggbb'; None for missing/transparent."""
    if c is None:
        return None
    try:
        from matplotlib.colors import to_hex, to_rgba
        if isinstance(c, str):
            s = c.strip()
            if s.startswith(("rgb(", "rgba(")):
                nums = [float(v) for v in s[s.index("(") + 1:-1].split(",")]
                if len(nums) == 4 and nums[3] == 0:
                    return None
                return to_hex(tuple(n / 255 for n in nums[:3]))
            if s.lower() in ("none", ""):
                return None
        rgba = to_rgba(c)
        if rgba[3] == 0:
            return None
        return to_hex(rgba[:3])
    except Exception:
        return None


def _n_finite(y: Any) -> int:
    try:
        arr = np.asarray(y, dtype=float)
        return int(np.isfinite(arr).sum())
    except Exception:
        return len(y) if hasattr(y, "__len__") else 0


def _norm_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _split_title(s: str | None) -> list[str]:
    if not s:
        return []
    parts = re.split(r"<br\s*/?>|\n", s)
    out = [_norm_text(re.sub(r"<[^>]+>", "", p)) for p in parts]
    return [p for p in out if p]


def _new_panel(i: int) -> dict[str, Any]:
    return {"index": i, "row": 0, "col": 0, "title_lines": [], "xlabel": "", "ylabel": "",
            "ylabel_right": "", "yscale": "linear", "n_secondary": 0, "ylim": None,
            "lines": {"left": [], "right": []}, "fills": {"left": [], "right": []},
            "markers": {"left": [], "right": []}, "scatter_n_points": 0,
            "scatter_n_colors": 0, "hlines": [], "vlines": [], "texts": [],
            "legend": [], "bars": 0}


def _finish(spec: dict[str, Any]) -> dict[str, Any]:
    for p in spec["panels"]:
        cols: set[str | None] = set()
        for side in ("left", "right"):
            for m in p["markers"][side]:
                cols.update(m["colors"])
        p["scatter_n_colors"] = len({c for c in cols if c})
        for side in ("left", "right"):
            p["fills"][side] = sorted({c for c in p["fills"][side] if c})
        p["hlines"] = sorted(p["hlines"])
        p["vlines"] = sorted(p["vlines"])
    return spec


# ------------------------------------------------------------- matplotlib ---
def capture_mpl(fn, *args, **kwargs) -> list:
    """Call a notebook plotting helper headlessly; return the Figures it made.

    plt.show / plt.close are no-ops during the call so helpers that end with
    show() (or close()) still hand back their figures. Caller closes them.
    """
    import matplotlib
    import matplotlib.pyplot as plt
    from unittest import mock

    before = set(plt.get_fignums())
    with mock.patch.object(plt, "show", lambda *a, **k: None), \
         mock.patch.object(plt, "close", lambda *a, **k: None):
        ret = fn(*args, **kwargs)
    figs = [plt.figure(n) for n in plt.get_fignums() if n not in before]
    if not figs and isinstance(ret, matplotlib.figure.Figure):
        figs = [ret]
    return figs


def mpl_spec(fig) -> dict[str, Any]:
    import matplotlib.collections as mcoll
    import matplotlib.patches as mpatches

    fig.canvas.draw()  # final positions (tight/constrained layout) only exist after draw
    groups: list[tuple[tuple[float, ...], list]] = []
    for ax in fig.axes:
        if ax.get_label() == "<colorbar>":
            continue
        key = tuple(round(v, 3) for v in ax.get_position().bounds)
        for k, axs in groups:
            if all(abs(a - b) < 0.01 for a, b in zip(k, key)):
                axs.append(ax)
                break
        else:
            groups.append((key, [ax]))
    groups.sort(key=lambda g: (-round(g[0][1] + g[0][3], 2), round(g[0][0], 2)))
    rows = sorted({round(k[1] + k[3], 2) for k, _ in groups}, reverse=True)
    cols = sorted({round(k[0], 2) for k, _ in groups})

    panels = []
    for i, (key, axs) in enumerate(groups):
        p = _new_panel(i)
        p["row"] = rows.index(round(key[1] + key[3], 2))
        p["col"] = cols.index(round(key[0], 2))
        p["n_secondary"] = len(axs) - 1
        for j, ax in enumerate(axs):
            side = "left" if j == 0 else "right"
            if j == 0:
                title = ax.get_title() or ax.get_title(loc="left") or ax.get_title(loc="right")
                p["title_lines"] = _split_title(title)
                p["xlabel"] = _norm_text(ax.get_xlabel())
                p["ylabel"] = _norm_text(ax.get_ylabel())
                p["yscale"] = ax.get_yscale()
                # only an EXPLICIT set_ylim (equalize_ylim, ylim_margin) is a
                # requirement; autoscaled limits are not compared
                p["ylim"] = None if ax.get_autoscaley_on() else [float(v) for v in ax.get_ylim()]
            elif not p["ylabel_right"]:
                p["ylabel_right"] = _norm_text(ax.get_ylabel())
            for ln in ax.get_lines():
                tr = ln.get_transform()
                xd, yd = ln.get_xdata(orig=True), ln.get_ydata(orig=True)
                try:
                    is_h = tr == ax.get_yaxis_transform(which="grid")
                    is_v = tr == ax.get_xaxis_transform(which="grid")
                except Exception:
                    is_h = is_v = False
                if is_h:
                    p["hlines"].append(float(np.asarray(yd, float)[0]))
                    continue
                if is_v:
                    try:
                        p["vlines"].append(float(np.asarray(xd, float)[0]))
                    except Exception:
                        p["vlines"].append(str(np.asarray(xd)[0]))
                    continue
                label = ln.get_label()
                label = None if str(label).startswith("_") else str(label)
                ls, mk = str(ln.get_linestyle()), str(ln.get_marker())
                if ls in ("None", "none", " ", "") and mk not in ("None", "none", ""):
                    p["markers"][side].append({"colors": [_hex(ln.get_markerfacecolor()) or _hex(ln.get_color())],
                                               "marker": mk, "n": _n_finite(yd)})
                    p["scatter_n_points"] += _n_finite(yd)
                else:
                    p["lines"][side].append({"color": _hex(ln.get_color()), "label": label, "n": _n_finite(yd)})
            for coll in ax.collections:
                if isinstance(coll, mcoll.PolyCollection):
                    for fc in coll.get_facecolor():
                        p["fills"][side].append(_hex(tuple(fc)))
                elif isinstance(coll, mcoll.PathCollection):
                    n = len(coll.get_offsets())
                    cs = {_hex(tuple(fc)) for fc in coll.get_facecolor()}
                    p["markers"][side].append({"colors": sorted(c for c in cs if c), "marker": "o", "n": n})
                    p["scatter_n_points"] += n
                elif isinstance(coll, mcoll.LineCollection):
                    for seg in coll.get_segments():
                        seg = np.asarray(seg)
                        if seg.shape[0] == 2 and seg[0, 0] == seg[1, 0]:
                            p["vlines"].append(float(seg[0, 0]))
                        elif seg.shape[0] == 2 and seg[0, 1] == seg[1, 1]:
                            p["hlines"].append(float(seg[0, 1]))
            p["bars"] += sum(isinstance(pt, mpatches.Rectangle) and pt.get_width() and pt.get_height()
                             for pt in ax.patches)
            p["texts"] += [_norm_text(t.get_text()) for t in ax.texts if _norm_text(t.get_text())]
            leg = ax.get_legend()
            if leg is not None:
                p["legend"] += [_norm_text(t.get_text()) for t in leg.get_texts()]
        panels.append(p)
    sup = getattr(fig, "_suptitle", None)
    return _finish({"suptitle": _norm_text(sup.get_text()) if sup else None,
                    "grid": [len(rows), len(cols)], "panels": panels})


# ----------------------------------------------------------------- plotly ---
def _axref(name: str) -> str:  # 'yaxis3' -> 'y3', 'yaxis' -> 'y'
    return name[0] + name[5:]


def _axname(ref: str) -> str:  # 'y3' -> 'yaxis3', 'y' -> 'yaxis'
    return ref[0] + "axis" + ref[1:]


def plotly_spec(fig) -> dict[str, Any]:
    fd = fig.to_dict() if hasattr(fig, "to_dict") else fig
    layout, data = fd.get("layout", {}) or {}, fd.get("data", []) or []
    xaxes = {k: (v or {}) for k, v in layout.items() if re.fullmatch(r"xaxis\d*", k)}
    yaxes = {k: (v or {}) for k, v in layout.items() if re.fullmatch(r"yaxis\d*", k)}
    xaxes.setdefault("xaxis", {})
    yaxes.setdefault("yaxis", {})
    colorway = (((layout.get("template") or {}).get("layout") or {}).get("colorway")
                or layout.get("colorway") or _PLOTLY_COLORWAY)

    # panel = primary yaxis (no 'overlaying') + its anchored xaxis
    prim = {k: v for k, v in yaxes.items() if not v.get("overlaying")}
    sec_of = {k: _axname(v["overlaying"]) for k, v in yaxes.items() if v.get("overlaying")}
    geo = {}
    for yk, yv in prim.items():
        xk = _axname(yv.get("anchor", "x")) if yv.get("anchor", "x") != "free" else "xaxis"
        xd = xaxes.get(xk, {}).get("domain", [0, 1])
        yd = yv.get("domain", [0, 1])
        geo[yk] = (xk, xd, yd)
    order = sorted(geo, key=lambda k: (-round(geo[k][2][1], 2), round(geo[k][1][0], 2)))
    rows = sorted({round(geo[k][2][1], 2) for k in geo}, reverse=True)
    cols = sorted({round(geo[k][1][0], 2) for k in geo})
    panel_of: dict[str, int] = {}
    panels = []
    for i, yk in enumerate(order):
        xk, xd, yd = geo[yk]
        p = _new_panel(i)
        p["row"], p["col"] = rows.index(round(yd[1], 2)), cols.index(round(xd[0], 2))
        p["xlabel"] = _norm_text(((xaxes[xk].get("title") or {}).get("text")) if isinstance(xaxes[xk].get("title"), dict) else xaxes[xk].get("title"))
        p["ylabel"] = _norm_text(((yaxes[yk].get("title") or {}).get("text")) if isinstance(yaxes[yk].get("title"), dict) else yaxes[yk].get("title"))
        p["yscale"] = "log" if yaxes[yk].get("type") == "log" else "linear"
        rng = yaxes[yk].get("range")
        p["ylim"] = [float(rng[0]), float(rng[1])] if rng else None
        secs = [s for s, t in sec_of.items() if t == yk]
        p["n_secondary"] = len(secs)
        if secs:
            t = yaxes[secs[0]].get("title")
            p["ylabel_right"] = _norm_text(t.get("text") if isinstance(t, dict) else t)
        panel_of[yk] = i
        for s in secs:
            panel_of[s] = i
        panel_of[xk + "|x"] = i
        panels.append(p)

    def side_of(yref: str) -> str:
        return "right" if _axname(yref) in sec_of else "left"

    for ti, tr in enumerate(data):
        ttype = tr.get("type", "scatter")
        yref = tr.get("yaxis", "y")
        pi = panel_of.get(_axname(yref))
        if pi is None:
            continue
        p, side = panels[pi], side_of(yref)
        y = tr.get("y", [])
        n = _n_finite(y) if y is not None else 0
        if ttype in ("scatter", "scattergl"):
            mode = tr.get("mode") or ("lines+markers" if n <= 20 else "lines")
            line = tr.get("line") or {}
            marker = tr.get("marker") or {}
            lc = _hex(line.get("color")) if line.get("color") is not None else _hex(colorway[ti % len(colorway)])
            fill = tr.get("fill")
            if fill and fill != "none":
                p["fills"][side].append(_hex(tr.get("fillcolor")) or lc)
            # width-0 / transparent lines are fill scaffolding (base + top of a
            # tonexty pair), not drawn lines; never count them as lines
            invisible = line.get("width") == 0 or ("color" in line and _hex(line.get("color")) is None)
            if "lines" in mode and not invisible:
                p["lines"][side].append({"color": lc, "label": tr.get("name"), "n": n})
            if "markers" in mode:
                mc = marker.get("color")
                if isinstance(mc, (list, tuple, np.ndarray)):
                    cs = sorted({c for c in (_hex(c) for c in mc) if c})
                else:
                    cs = [_hex(mc) if mc is not None else lc]
                p["markers"][side].append({"colors": cs, "marker": str(marker.get("symbol", "circle")), "n": n})
                p["scatter_n_points"] += n
            if "text" in mode:
                txt = tr.get("text")
                if isinstance(txt, (list, tuple, np.ndarray)):
                    p["texts"] += [_norm_text(str(t)) for t in txt if _norm_text(str(t))]
                elif txt:
                    p["texts"].append(_norm_text(str(txt)))
            if tr.get("showlegend", True) and tr.get("name"):
                p["legend"].append(_norm_text(tr["name"]))
        elif ttype in ("bar", "histogram"):
            p["bars"] += len(tr.get("x") or tr.get("y") or [])
            if tr.get("showlegend", True) and tr.get("name"):
                p["legend"].append(_norm_text(tr["name"]))

    for sh in layout.get("shapes") or []:
        if sh.get("type") != "line":
            continue
        xref, yref = str(sh.get("xref", "x")), str(sh.get("yref", "y"))
        xdom, ydom = ("domain" in xref or xref == "paper"), ("domain" in yref or yref == "paper")
        if xdom and sh.get("x0") == 0 and sh.get("x1") == 1 and not ydom:
            pi = panel_of.get(_axname(yref.split()[0]))
            if pi is not None:
                panels[pi]["hlines"].append(float(sh["y0"]))
        elif ydom and sh.get("y0") == 0 and sh.get("y1") == 1 and not xdom:
            pi = panel_of.get(_axname(xref.split()[0]) + "|x")
            if pi is not None:
                try:
                    panels[pi]["vlines"].append(float(sh["x0"]))
                except (TypeError, ValueError):
                    panels[pi]["vlines"].append(str(sh["x0"]))

    for an in layout.get("annotations") or []:
        text = an.get("text", "")
        xref, yref = str(an.get("xref", "x")), str(an.get("yref", "y"))
        if xref == "paper" and yref == "paper":
            x, y = float(an.get("x", 0)), float(an.get("y", 0))
            for i, yk in enumerate(order):
                _, xd, yd = geo[yk]
                if xd[0] - 1e-6 <= x <= xd[1] + 1e-6 and abs(y - yd[1]) < 0.06:
                    panels[i]["title_lines"] = _split_title(text)
                    break
                if xd[0] <= x <= xd[1] and yd[0] <= y <= yd[1]:
                    panels[i]["texts"].append(_norm_text(re.sub(r"<[^>]+>", "", text)))
                    break
        else:
            pi = panel_of.get(_axname(yref.split()[0]))
            if pi is not None:
                panels[pi]["texts"].append(_norm_text(re.sub(r"<[^>]+>", "", text)))

    title = layout.get("title")
    sup = title.get("text") if isinstance(title, dict) else title
    return _finish({"suptitle": _norm_text(sup) if sup else None,
                    "grid": [len(rows), len(cols)], "panels": panels})


# ------------------------------------------------------------------- diff ---
def diff_spec(golden: dict[str, Any], got: dict[str, Any], *, colors: bool = True,
              ylim_rtol: float = 0.02) -> list[str]:
    """Return findings, 'ERR ...' (must fix) or 'WARN ...' (judge, then ledger).

    colors=False relaxes color equality when the user explicitly chose the host
    palette over the notebook's; that choice belongs in the ledger, not here.
    """
    out: list[str] = []
    ga, gb = golden["panels"], got["panels"]
    if len(ga) == 1 and len(gb) == 1:
        # single panel: ax.set_title and layout.title are the same slot -> compare the union
        import copy
        ga, gb = copy.deepcopy(ga), copy.deepcopy(gb)
        for spec, panels in ((golden, ga), (got, gb)):
            panels[0]["title_lines"] = _split_title(spec.get("suptitle")) + panels[0]["title_lines"]
    elif _norm_text(golden.get("suptitle")) != _norm_text(got.get("suptitle")):
        out.append(f"WARN suptitle: notebook {golden.get('suptitle')!r} vs port {got.get('suptitle')!r}")
    if len(ga) != len(gb):
        out.append(f"ERR panel count: notebook {len(ga)} vs port {len(gb)} (grid {golden['grid']} vs {got['grid']})")
    for pa, pb in zip(ga, gb):
        tag = f"panel {pa['index']} ({pa['title_lines'][0] if pa['title_lines'] else '?'})"
        if pa["title_lines"] != pb["title_lines"]:
            out.append(f"ERR {tag} title: notebook {pa['title_lines']} vs port {pb['title_lines']}")
        if (pa["n_secondary"] > 0) != (pb["n_secondary"] > 0):
            out.append(f"ERR {tag} secondary y-axis: notebook {pa['n_secondary']} vs port {pb['n_secondary']}")
        for side in ("left", "right"):
            la, lb = pa["lines"][side], pb["lines"][side]
            if len(la) != len(lb):
                out.append(f"ERR {tag} {side} lines: notebook {len(la)} vs port {len(lb)}")
            elif colors:
                ca, cb = sorted(filter(None, (l["color"] for l in la))), sorted(filter(None, (l["color"] for l in lb)))
                if ca != cb:
                    out.append(f"ERR {tag} {side} line colors: notebook {ca} vs port {cb}")
            fa, fb = set(pa["fills"][side]), set(pb["fills"][side])
            if fa != fb:
                if colors or bool(fa) != bool(fb):
                    out.append(f"ERR {tag} {side} fill colors: notebook {sorted(fa)} vs port {sorted(fb)}")
            na, nb = sum(m["n"] for m in pa["markers"][side]), sum(m["n"] for m in pb["markers"][side])
            if na != nb:
                out.append(f"ERR {tag} {side} marker points: notebook {na} vs port {nb}")
        if pa["scatter_n_colors"] != pb["scatter_n_colors"] and colors:
            out.append(f"ERR {tag} distinct point colors: notebook {pa['scatter_n_colors']} vs port {pb['scatter_n_colors']}"
                       + (" (per-point color encoding collapsed)" if pb["scatter_n_colors"] < pa["scatter_n_colors"] else ""))
        for kind in ("hlines", "vlines"):
            va, vb = pa[kind], pb[kind]
            same = len(va) == len(vb) and all(
                (isinstance(a, str) and str(a) == str(b)) or
                (not isinstance(a, str) and not isinstance(b, str) and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9))
                for a, b in zip(va, vb))
            if not same:
                out.append(f"ERR {tag} {kind}: notebook {va} vs port {vb}")
        ta, tb = set(pa["texts"]), set(pb["texts"])
        if ta - tb:
            out.append(f"ERR {tag} texts missing in port: {sorted(ta - tb)[:10]}")
        if tb - ta:
            out.append(f"WARN {tag} extra texts in port: {sorted(tb - ta)[:10]}")
        if pa["yscale"] != pb["yscale"]:
            out.append(f"ERR {tag} yscale: notebook {pa['yscale']} vs port {pb['yscale']}")
        if pa["bars"] != pb["bars"]:
            out.append(f"WARN {tag} bars: notebook {pa['bars']} vs port {pb['bars']}")
        if len(pa["legend"]) != len(pb["legend"]):
            out.append(f"WARN {tag} legend entries: notebook {len(pa['legend'])} vs port {len(pb['legend'])}")
        for k in ("xlabel", "ylabel", "ylabel_right"):
            if pa[k] != pb[k]:
                out.append(f"WARN {tag} {k}: notebook {pa[k]!r} vs port {pb[k]!r}")
        if pa["ylim"] and pb["ylim"]:
            span = abs(pa["ylim"][1] - pa["ylim"][0]) or 1.0
            if any(abs(a - b) > ylim_rtol * span for a, b in zip(pa["ylim"], pb["ylim"])):
                out.append(f"WARN {tag} ylim: notebook {pa['ylim']} vs port {pb['ylim']}")
        elif pa["ylim"] and not pb["ylim"]:
            out.append(f"WARN {tag} ylim: notebook fixed {pa['ylim']}, port autoranges (equalize_ylim/ylim_margin lost?)")
    return out


def save_spec(spec: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(spec, indent=1, default=str), encoding="utf-8")


# ---------------------------------------------------------- contact sheet ---
def _png_from_mpl(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
    return buf.getvalue()


def _png_from_plotly(fig, fallback_html: Path) -> bytes | None:
    try:
        return fig.to_image(format="png", scale=1)
    except Exception as e:  # kaleido missing or broken: hand the agent an HTML to screenshot
        fallback_html.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(fallback_html), include_plotlyjs="cdn")
        print(f"plotly PNG unavailable ({type(e).__name__}); wrote {fallback_html} - screenshot it "
              f"(dash-ui-verify snap.py / Playwright) and rerun: fig_spec.py sheet mpl.png plotly.png out.png")
        return None


def contact_sheet(mpl_fig, plotly_fig, out_png: str | Path) -> Path:
    """mpl PNG | plotly PNG side by side with labels. Read the PNG before claiming parity."""
    out = Path(out_png)
    left = _png_from_mpl(mpl_fig)
    right = _png_from_plotly(plotly_fig, out.with_suffix(".plotly.html"))
    return stitch(left, right, out)


def stitch(left_png: bytes | str | Path, right_png: bytes | str | Path | None, out_png: str | Path) -> Path:
    from PIL import Image, ImageDraw

    def _open(x):
        return Image.open(io.BytesIO(x) if isinstance(x, bytes) else x).convert("RGB")

    a = _open(left_png)
    b = _open(right_png) if right_png is not None else Image.new("RGB", a.size, (235, 235, 235))
    h = max(a.height, b.height)
    scale = lambda im: im.resize((int(im.width * h / im.height), h))
    a, b = scale(a), scale(b)
    strip = 28
    sheet = Image.new("RGB", (a.width + b.width + 12, h + strip), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    d.text((6, 6), "NOTEBOOK (matplotlib)", fill=(0, 0, 0))
    d.text((a.width + 18, 6), "PORT (plotly)" if right_png is not None else "PORT (plotly) - PNG unavailable, see .plotly.html",
           fill=(0, 0, 0))
    sheet.paste(a, (0, strip))
    sheet.paste(b, (a.width + 12, strip))
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


# -------------------------------------------------------------------- CLI ---
def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "diff":
        a = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        b = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        findings = diff_spec(a, b, colors="--no-colors" not in argv)
        print("\n".join(findings) or "no findings: structural parity")
        return 1 if any(f.startswith("ERR") for f in findings) else 0
    if len(argv) == 4 and argv[0] == "sheet":
        print(stitch(argv[1], argv[2], argv[3]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
