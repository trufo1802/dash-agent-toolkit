"""Layout policy + lint for Plotly figures ported from matplotlib (the overlap/size class).

matplotlib lays the figure out for you (tight_layout, bbox_inches="tight", figsize that
grows with rows). Plotly does not: margins, legend, title and subplot-title positions are
fixed numbers in paper coordinates and the height is a constant. Porting without an
explicit policy produces legends over subplot titles, titles over titles, 12 panels in
450 px, rotated dates under the legend. Three tools:

  layout_policy(...)       one function every twin calls -> make_subplots kwargs +
                           update_layout kwargs derived from rows/cols/title lines/legend mode
  lint_layout(fig)         static, no browser: geometry rules on the figure dict
  OVERLAP_JS / overlaps_in_page(page, selector)
                           rendered DOM: bounding boxes of legend, figure title, subplot
                           titles, axis titles, colorbars -> intersecting pairs. Pixels beat
                           heuristics; run it through the dash-ui-verify page fixture (or any
                           Playwright page) whenever a browser is available.

Usage:
    sub, lay = layout_policy(nrows=4, ncols=3, title_lines=2, legend="below")
    fig = make_subplots(rows=4, cols=3, subplot_titles=titles, **sub)
    ...
    fig.update_layout(**lay)
    assert not [m for m in lint_layout(fig) if m.startswith("ERR")]
    assert not overlaps_in_page(page, "#graph-cta")["overlaps"]
"""
from __future__ import annotations

import re
from typing import Any

LINE_PX = 22          # one line of title text at ~11-13 px font incl. leading
ROW_PX = 300          # ~ matplotlib figsize_rowscale=4in at 75 dpi, per subplot row
TICK_ROT_PX = 90      # vertical date tick labels need this much bottom room


def layout_policy(nrows: int, ncols: int, *, title_lines: int = 1, suptitle_lines: int = 0,
                  legend: str = "below", row_px: int = ROW_PX, xtick_rotated: bool = False,
                  xlabel: bool = False, right_axis: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (make_subplots kwargs, update_layout kwargs) for a grid port.

    legend: "below" (horizontal under the grid - mpl legend outside), "right" (vertical,
    outside right), "none", or "inside" (per-panel legends handled by the twin).
    All numbers are pixels converted to paper fractions against the computed height, so the
    same policy holds for 1 row or 12.
    """
    top = 20 + LINE_PX * suptitle_lines + LINE_PX * title_lines + 6
    tick_px = TICK_ROT_PX if xtick_rotated else 20
    bottom = 40 + tick_px + (LINE_PX if xlabel else 0)
    legend_px = 0
    if legend == "below":
        legend_px = 34
        bottom += legend_px
    # the gap between rows must hold the upper row's tick labels (+ x title) AND the
    # lower row's title lines; rows keep their full row_px (mpl grows the canvas, so do we)
    gap_px = (tick_px + (LINE_PX if xlabel else 0) + LINE_PX * title_lines + 16) if nrows > 1 else 0
    height = top + bottom + row_px * nrows + gap_px * (nrows - 1)
    vspace = gap_px / (height - top - bottom) if nrows > 1 else 0.0
    sub = {"vertical_spacing": vspace, "horizontal_spacing": 0.08 if right_axis else 0.05}
    lay: dict[str, Any] = {
        "height": height,
        "margin": {"t": top, "b": bottom, "l": 60, "r": 70 if right_axis else 30},
        "autosize": True,
    }
    if suptitle_lines:
        lay["title"] = {"y": 1 - 8 / height, "yanchor": "top", "x": 0.5, "xanchor": "center"}
    if legend == "below":
        lay["legend"] = {"orientation": "h", "yanchor": "top", "y": -(bottom - legend_px + 6) / (height - top - bottom),
                         "xanchor": "left", "x": 0}
    elif legend == "right":
        lay["legend"] = {"orientation": "v", "yanchor": "top", "y": 1, "xanchor": "left", "x": 1.02}
        lay["margin"]["r"] = max(lay["margin"]["r"], 160)
    elif legend == "none":
        lay["showlegend"] = False
    return sub, lay


# ------------------------------------------------------------------- static lint ---
def _lines(text: str | None) -> int:
    return len([p for p in re.split(r"<br\s*/?>|\n", text or "") if p.strip()]) if text else 0


def lint_layout(fig, *, min_row_px: int = 180) -> list[str]:
    """Geometry rules on the figure dict. 'ERR' = will overlap/clip; 'WARN' = likely."""
    fd = fig.to_dict() if hasattr(fig, "to_dict") else fig
    lay = fd.get("layout", {}) or {}
    out: list[str] = []
    yaxes = {k: (v or {}) for k, v in lay.items() if re.fullmatch(r"yaxis\d*", k) and not (v or {}).get("overlaying")}
    xaxes = {k: (v or {}) for k, v in lay.items() if re.fullmatch(r"xaxis\d*", k)}
    tops = sorted({round((v.get("domain") or [0, 1])[1], 3) for v in yaxes.values()}, reverse=True) or [1.0]
    bottoms = sorted({round((v.get("domain") or [0, 1])[0], 3) for v in yaxes.values()}, reverse=True) or [0.0]
    nrows = len(tops)
    height = lay.get("height")
    margin = {"t": 100, "b": 80, "l": 80, "r": 80, **(lay.get("margin") or {})}
    anns = [a for a in (lay.get("annotations") or []) if a.get("xref") == "paper" and a.get("yref") == "paper"]
    sub_titles = [a for a in anns if any(abs(float(a.get("y", -9)) - t) < 0.06 for t in tops)]
    title = lay.get("title")
    title_text = title.get("text") if isinstance(title, dict) else title
    title_lines = _lines(title_text)
    sub_lines = max([_lines(a.get("text")) for a in sub_titles] or [0])
    rotated = any(x.get("tickangle") not in (None, 0) for x in xaxes.values())
    xlab = any((x.get("title") or {}).get("text") if isinstance(x.get("title"), dict) else x.get("title")
               for x in xaxes.values())

    if height is None:
        out.append(f"WARN height unset: Dash renders 450 px for {nrows} row(s); set height = policy")
        plot_h = 450 - margin["t"] - margin["b"]
    else:
        plot_h = height - margin["t"] - margin["b"]
        if plot_h / nrows < min_row_px:
            out.append(f"ERR squashed: {plot_h / nrows:.0f} px per row for {nrows} rows (< {min_row_px}); "
                       f"height should scale with rows (layout_policy)")

    if nrows > 1 and sub_titles:
        gaps = [bottoms[i] - tops[i + 1] for i in range(nrows - 1)]
        gap_px = min(gaps) * plot_h if gaps else 0
        need = (TICK_ROT_PX if rotated else 20) + (LINE_PX if xlab else 0) + LINE_PX * sub_lines + 10
        if gap_px < need:
            out.append(f"ERR subplot titles collide with the row above's tick labels: gap {gap_px:.0f} px < {need} px "
                       f"needed ({'rotated ticks + ' if rotated else ''}{sub_lines}-line titles); "
                       f"size vertical_spacing/height with layout_policy")
    if sub_titles and sub_lines * LINE_PX + 10 > margin["t"] - (title_lines * LINE_PX if title_lines else 0):
        out.append(f"ERR top margin {margin['t']} px too small for {sub_lines}-line subplot titles"
                   + (f" plus a {title_lines}-line figure title" if title_lines else ""))
    if title_lines and sub_titles:
        ty = title.get("y") if isinstance(title, dict) else None
        if ty is None or (isinstance(title, dict) and title.get("yanchor") not in ("top",)):
            out.append("ERR figure title shares the top band with subplot titles: put the section title in the "
                       "page (html.H4) or set title.y/yanchor='top' + margin.t = policy")

    leg = lay.get("legend") or {}
    show = lay.get("showlegend", True) and any(t.get("showlegend", True) and t.get("name") for t in fd.get("data", []))
    if show:
        if leg.get("orientation") == "h":
            y = float(leg.get("y", -0.1))
            if 0.93 <= y <= 1.12 and sub_titles:
                out.append(f"ERR horizontal legend at y={y} sits on the top-row subplot titles; move it below "
                           f"(policy legend='below') or above the titles with yanchor='bottom' and room in margin.t")
            if y < 0:
                need_px = 30 + (TICK_ROT_PX if rotated else 20) + (LINE_PX if xlab else 0)
                if -y * plot_h < need_px:
                    out.append(f"WARN horizontal legend at y={y} ({-y * plot_h:.0f} px below plot) collides with "
                               f"x tick labels/title (need ~{need_px} px); lower y or raise margin.b")
                if margin["b"] < need_px + 34:
                    out.append(f"WARN margin.b={margin['b']} too small for a legend below rotated/titled x axis (~{need_px + 34})")
        else:
            x = float(leg.get("x", 1.02))
            if x >= 1 and margin["r"] < 120:
                out.append(f"WARN vertical legend outside right (x={x}) with margin.r={margin['r']}: entries clip; "
                           f"margin.r >= 160 or legend='below'")
    texts = [a.get("text") for a in sub_titles]
    if len(texts) != len(set(texts)) and texts:
        out.append("WARN duplicate subplot titles (same text on several panels)")
    return out


# ------------------------------------------------------------- rendered overlap ---
# Plotly.js DOM: g.legend | g.g-gtitle (figure title) | g.infolayer g.annotation (subplot titles,
# text annotations) | g.g-xtitle / g.g-ytitle / g.g-x2title ... (axis titles) | g.colorbar |
# g.xaxislayer-above g.xtick text (tick labels). Verified against plotly.js 2.x.
OVERLAP_JS = r"""
(sel) => {
  const root = (sel && document.querySelector(sel)) || document;
  const pick = (q, label) => [...root.querySelectorAll(q)].map((el, i) => {
    const r = el.getBoundingClientRect();
    return {label: label + '#' + i, x0: r.left, y0: r.top, x1: r.right, y1: r.bottom,
            text: (el.textContent || '').trim().slice(0, 40)};
  }).filter(b => b.x1 - b.x0 > 0 && b.y1 - b.y0 > 0);
  const boxes = [
    ...pick('g.legend', 'legend'),
    ...pick('g.g-gtitle', 'title'),
    ...pick('g.infolayer g.annotation', 'annotation'),
    ...pick('g.infolayer g[class$="title"]:not(.g-gtitle)', 'axis-title'),
    ...pick('g.colorbar', 'colorbar'),
    ...pick('g.xaxislayer-above g.xtick text', 'xtick'),
  ];
  const kind = b => b.label.split('#')[0];
  const out = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (kind(a) === 'xtick' && kind(b) === 'xtick') continue;   // tick crowding is a separate check
    const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
    if (w > 2 && h > 2) out.push({a: a.label, b: b.label, px: Math.round(w * h), text_a: a.text, text_b: b.text});
  }
  const gd = (root.matches && root.matches('.js-plotly-plot')) ? root : (root.querySelector('.js-plotly-plot') || root);
  const rect = gd.getBoundingClientRect();
  const n_sub = root.querySelectorAll('g.cartesianlayer g.subplot').length;
  return {overlaps: out, n_subplots: n_sub, width: Math.round(rect.width), height: Math.round(rect.height),
          px_per_row_hint: n_sub ? Math.round(rect.height / Math.max(1, Math.round(Math.sqrt(n_sub)))) : null};
}
"""


def overlaps_in_page(page, selector: str | None = None) -> dict[str, Any]:
    """Playwright: evaluate OVERLAP_JS on a rendered Graph. Wait for `.js-plotly-plot .main-svg` first."""
    page.wait_for_selector((selector + " " if selector else "") + ".js-plotly-plot .main-svg", timeout=15000)
    return page.evaluate(OVERLAP_JS, selector)


def describe_overlaps(result: dict[str, Any]) -> str:
    rows = [f"{o['a']} x {o['b']} ({o['px']} px^2): {o['text_a']!r} / {o['text_b']!r}" for o in result.get("overlaps", [])]
    return "\n".join(rows) or "no overlaps"
