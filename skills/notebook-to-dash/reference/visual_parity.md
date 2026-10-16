# Visual parity: porting the notebook's FIGURES, not just its numbers

Companion to `mpl_plotly_map.md` (construct-by-construct table). This file is the
procedure + the recipes for the constructs that quant plotting helpers actually use,
written from a real failed port (12-panel FX grid with L1/R1 axes, threshold fills
and two-line titles came back as single black lines; a per-point colored scatter
came back all blue; a Styler table came back as a wrong heatmap).

Contents: 1 helper-twin contract · 2 goldens · 3 recipes · 4a layout lint · 4 contact sheet · 5 failure table · 6 kwargs as controls

## 1. The helper-twin contract (port the HELPER, not the cell)

A notebook cell like

```python
fv.plot_df_subplots([df0, df1, df2], axis=["L1","R1","L1"], threshold_fill=[0,None,None],
                    title_last_yymmdd=True, equalize_ylim=False)
```

is one line; the figure's definition is the 200–400-line helper behind it (axis tags,
fill rules, color cycle, title composition, hline/vline lists, legend mode). Porting
the cell means re-imagining the figure. Porting the helper means translating it.

Rules:
- One twin per helper actually called (inventory: `python templates/plot_calls.py nb.ipynb --receiver fv`).
  Same function name, same signature, same kwarg semantics, in `<pkg>/plotting/<helper>_plotly.py`.
  Return `go.Figure` (tables: a Dash component). No Dash imports in figure twins.
- Read the helper source top to bottom BEFORE writing the twin; map every branch
  (`if axis[i].startswith("R")`, `if threshold_fill[i] is not None`, ...) to a Plotly construct.
- Every kwarg in the inventory is handled or raises `NotImplementedError("<kwarg>")`.
  A kwarg silently ignored is how `threshold_fill` disappears without an error.
- The page calls the twin with the notebook cell's arguments VERBATIM. Controls
  default to those values. "Improvements" (different palette, dropped labels,
  merged panels) are ledger items `[I#]`, proposed, never substituted.
- Visual encodings are requirements: axis assignment, per-series and per-point
  color, fills and their colors, reference lines, text labels, title lines, scale,
  explicitly fixed limits. House palette applies only where the notebook used
  matplotlib defaults AND color carries no meaning — and it is ledgered.

## 2. Goldens: structural figure specs from the NOTEBOOK helper

```python
from fig_spec import capture_mpl, mpl_spec, save_spec
figs = capture_mpl(fv.plot_df_subplots, dfs, axis=[...], threshold_fill=[...], title_last_yymmdd=True)
save_spec(mpl_spec(figs[0]), "tests/parity/golden_fig_cell397.json")
```

- Run this in the NOTEBOOK's env (the helper imports it). Headless: `MPLBACKEND=Agg`.
- Inputs = the same frozen snapshot the numeric gate uses (Step 1). A golden harvested
  on live data drifts tomorrow.
- Goldens come from the mpl helper only — never from the twin (circular, permanently green).
- One golden per notebook figure cell. Name it by cell index.
- `plotly_spec(twin(...))` + `diff_spec(golden, got)` → `ERR` lines must be empty; `WARN`
  lines are judged and ledgered (legend count, xlabel text, extra texts).
  `diff_spec(..., colors=False)` only when the user chose the host palette on record.

## 3. Recipes (helper construct → Plotly twin)

**a. Subplot grid with per-DataFrame axis tags (`L1`/`R1`/`R2`)**
`make_subplots(rows, cols, specs=[[{"secondary_y": True}]*cols]*rows, subplot_titles=...)`;
trace → `secondary_y=tag.startswith("R")`. A third ruler (`R2`) has no grid-native twin:
add `layout.yaxisN = dict(overlaying="y<k>", side="right", anchor="free", position=...)` per
panel, or translate to hover fields (`mpl_plotly_map.md` principle) — ledger either way.

**b. Threshold fill (`fill_between(x, y, thr, where=y>=thr, color="green")` + red below)**
Compute in the COMPUTE layer, not the twin: `up = np.where(y >= thr, y, thr)`,
`dn = np.where(y < thr, y, thr)`, `base = np.full_like(y, thr)`. Per color: a base trace
(`line.width=0, showlegend=False, hoverinfo="skip"`) then the clipped trace with
`fill="tonexty"`, `fillcolor="rgba(0,128,0,0.3)"` (same alpha as the helper). Then
`fig.add_hline(y=thr, row=r, col=c)` if the helper drew the threshold line. If the helper's
`where=` left NaN gaps, keep NaN instead of clipping so silhouettes match.

**c. Two-line titles (`title_last_yymmdd`, `"MXN (261014)\ny = 26 + 0.23X"`)**
Join with `<br>` in `subplot_titles`; the spec compares title LINES, so never flatten.
Give rows room: `vertical_spacing >= 0.08 + 0.02*extra_lines`, annotation `font.size=11`.

**d. Named/tab colors and per-DataFrame cycles**
`matplotlib.colors.to_hex("tab:blue")` → explicit `line.color`. Never leave `line.color`
unset: Plotly's colorway differs from tab10 and cycles per trace, not per DataFrame.

**e. Per-point colored scatter with point labels (`plot_series_scatter(annotate=True)`)**
One trace: `mode="markers+text"`, `marker.color=[...]` (list, one per point),
`text=[labels]`, `textposition="top center"`, `textfont.color=[...]` (same list), `opacity`
from the helper's alpha. `add_hline(0)` / `add_vline(0)` for the axes crosshair. If the
notebook's labels overlap, so do the page's — decluttering is an `[I#]`, not a default.

**f. Regression subplots with last-point marker (red X)**
Scatter trace + fit line trace (coefficients from the parity-tested compute layer) +
`go.Scatter(mode="markers", marker=dict(symbol="x", color="red", size=10))` for the
highlighted point. Title = `f"{name} ({ymd})<br>y = {b:.2g} + {m:.2g}X"`.

**g. `equalize_ylim` / `ylim_margin` / shared limits**
Explicit `fig.update_yaxes(range=[lo, hi], row=r, col=c)` from the SAME numbers the helper
computed (port that block verbatim). Pair with axis-level `uirevision` keyed on the data
window (dash-gotchas-review P6) or zoom resets will swallow it.

**h. `hline` / `vline` lists, `legend` modes**
Per-subplot lists → `add_hline/add_vline(row=, col=)`. `legend="first"|"last"|None|"all"` →
`showlegend` per trace; Plotly ≥5.15 supports per-subplot legends (`legend="legend2"`)
if the helper drew one per panel.

**i. Styler tables (`fv.color_table(df.T)`) → Dash**
Do not re-derive the colormap. Reuse the Styler's own computed CSS:
```python
sty = fv.color_table(tbl.T); sty._compute()           # pandas Styler, private but stable
ctx = sty.ctx                                        # {(row_i, col_j): [("background-color", "#..."), ...]}
```
→ `dash_table.DataTable(data=..., style_data_conditional=[{"if": {"row_index": i, "column_id": c},
"backgroundColor": bg, "color": fg}, ...])`, numbers formatted with the Styler's format
(`sty._display_funcs`) or the helper's own formatter. Keep the notebook's orientation (`.T`)
and column order. A heatmap trace is NOT a table twin.

**j. Figure title colliding with subplot titles** (observed: "By asset: irs_tr (1Y)" printed
over "EUR") — put section titles in the page layout (`html.H4`) and leave `layout.title`
empty; if a figure title is required, `title=dict(y=0.995, yanchor="top")` and
`margin.t = 60 + 20 * n_title_lines`.

**k. Panel height and layout geometry** — mpl `figsize=(5*ncols, 4*nrows)` + `tight_layout()`
grows and packs the canvas; Plotly's height, margins, legend and title positions are
constants. Do not tune them per figure: every twin calls ONE `layout_policy(nrows, ncols,
title_lines=, legend=, xtick_rotated=, ...)` from `templates/layout_lint.py` and passes its two
dicts to `make_subplots(**sub)` / `fig.update_layout(**lay)`. It derives height from rows
(~300 px each), the inter-row gap from the upper row's tick labels plus the lower row's title
lines, top margin from title lines, legend placement (`"below"` horizontal under the grid,
`"right"` vertical with `margin.r`), and the `dcc.Graph` gets `style={"height": f"{lay['height']}px"}`.
Rotated date ticks cost ~90 px per row, exactly as in mpl; Plotly's date axis seldom needs
rotation, so keep `tickangle` only if the notebook's rotation is a requirement (ledger it).

**l. Figure chrome** (`facecolor="beige"`, grid, spines) → `paper_bgcolor`/`plot_bgcolor`,
`showgrid`. Chrome may follow the host theme — ledger it as `[I#]`; data encodings may not.

## 4a. Layout lint — overlaps and sizes without a round-trip

```python
from layout_lint import lint_layout, overlaps_in_page, describe_overlaps
assert not [m for m in lint_layout(fig) if m.startswith("ERR")]        # static: figure dict only
res = overlaps_in_page(page, "#graph-cta")                             # rendered: Playwright page
assert not res["overlaps"], describe_overlaps(res)
```
`lint_layout` reads geometry from the figure dict: px per row, inter-row gap vs tick labels +
title lines, figure title sharing the top band with subplot titles, horizontal legend at
`y≈1` on the top-row titles, legend below colliding with rotated ticks, vertical legend
without `margin.r`. `overlaps_in_page` measures the real SVG (`g.legend`, `g.g-gtitle`,
`g.infolayer g.annotation`, axis titles, colorbars, x tick labels) and returns intersecting
pairs with their text — one Dash Graph at a time, after `.js-plotly-plot .main-svg` exists.
Run it in Step 7 for every Graph on the page; the static lint runs in Step 4 for every twin.

## 4. Contact sheet — the agent's eyes

```python
from fig_spec import contact_sheet
contact_sheet(mpl_fig, plotly_fig, "tests/parity/artifacts/cell397_sheet.png")
```
Needs `kaleido` for the Plotly PNG (`<env-python> -m pip install -U kaleido`); without it the
script writes `*.plotly.html` next to the output — screenshot it (dash-ui-verify `snap.py`
or a throwaway Playwright page) and stitch with `python fig_spec.py sheet mpl.png plotly.png out.png`.
Read the PNG before claiming visual parity. The spec diff catches structure; the sheet
catches what the spec does not encode (line width, label overlap, date formatting).

## 5. Failure table

| Symptom on the page | Cause | Fix |
|---|---|---|
| Every point / every line the same blue | twin left `marker.color`/`line.color` unset, or "house palette" rule applied to a color ENCODING | recipe d/e; `diff_spec` reports `distinct point colors N vs 1` |
| Right-axis series flat or missing | grid built without `specs=[[{"secondary_y": True}]]` | recipe a; spec `secondary y-axis 1 vs 0` |
| Green/red bands gone | `threshold_fill` kwarg ignored | recipe b; spec `fill colors [...] vs []` |
| Title lost its second line / dates | `title_last_yymmdd` block not ported | recipe c; spec `title [...] vs [...]` |
| Table colors / layout wrong | colormap re-derived by hand, or table drawn as a heatmap | recipe i |
| Section title overprints first subplot | `layout.title` + `subplot_titles` share the top margin | recipe j |
| 12 panels squashed, unreadable | fixed Graph height | recipe k |
| Legend explodes with 36 entries | per-trace `showlegend` default | recipe h |
| Numbers right, picture wrong, no test red | no visual gate | Step 4 of SKILL.md: golden spec + `diff_spec` + sheet |

## 6. Exposing helper kwargs as page controls (`[C#]`)

The user names which kwargs become controls ("make `threshold_fill` and `legend` dropdowns,
`ncols` a dropdown, add a recompute button"). Because the twin has the helper's signature,
a control is nothing more than a kwarg bound to a widget — no new code path, no new
interpretation of the kwarg, and an mpl oracle at every value.

| Kwarg shape in the helper | Widget | Options from | Default |
|---|---|---|---|
| `Literal[...]` / documented string set (`legend='first'|'last'|'all'|None`, `index_join`) | dropdown | the type hint / docstring / the `if kw == ...` branches | notebook cell value |
| `bool` (`equalize_ylim`, `title_last_yymmdd`, `const_reg`) | switch / checklist | — | notebook cell value |
| small int (`ncols`, `n_cols`) | dropdown of ints (or slider) | sensible range around the notebook value, stated as `[I#]` | notebook cell value |
| per-DataFrame list (`axis=["L1","R1",...]`, `threshold_fill=[0,None,...]`, `color`) | one dropdown per DataFrame, labelled by `dfs_name[i]` | tag grammar (`L1/R1/R2`) or the helper's accepted levels | notebook cell list, element-wise |
| scalar level (`threshold=0`) | numeric input | — | notebook value |
| data-selection args (`ymd_start`, `overlap_fx_equity`, window) | date picker / dropdown | the frozen snapshot's range / the notebook's universe | notebook value; changes COMPUTE → numeric parity at a non-default value too |
| "rerun"/"export" | button | — | n/a; action calls a compute-module function, nothing else |
| always | "reset to notebook" button | — | restores every control to the cell's values |

Callback pattern — pass-through, no interpretation, defaults frozen next to the twin call:

```python
NOTEBOOK_KWARGS = dict(axis=["L1", "R1", "R1", "R1"], threshold_fill=[None, None, None, None],
                       title_last_yymmdd=True, legend="all")          # the cell, verbatim

@callback(Output("graph-cta", "figure"),
          Input("ctl-legend", "value"), Input("ctl-threshold-0", "value"), ...)
def _render(legend, thr0, ...):
    controls = {"legend": legend, "threshold_fill": [thr0, None, None, None]}
    return fvp.plot_df_subplots(*DATA, **{**NOTEBOOK_KWARGS, **controls})  # twin interprets kwargs
```

Gate: for every `[C#]`, one non-default golden captured from the mpl helper
(`capture_mpl(fv.plot_df_subplots, *DATA, **{**NOTEBOOK_KWARGS, "legend": "first"})`) and
one `diff_spec` of the twin at that value — an entry per control in `FIGURES` of
`test_visual_parity.py`. With default values the page must reproduce the notebook exactly
(iron rule); the controls only extend it. Store the "reset" defaults in ONE place
(`NOTEBOOK_KWARGS`), never re-typed in the layout.

Prompt lines that make this unambiguous (one per control):
`[C1] threshold_fill -> dropdown per DataFrame, options {None, 0}, default as in the notebook`
`[C2] legend -> dropdown {None, first, last, all}` · `[C3] ncols -> dropdown {2,3,4}` ·
`[C4] button "recompute suridx" -> reruns compute_im_suridx_and_used_lists on the current controls`
