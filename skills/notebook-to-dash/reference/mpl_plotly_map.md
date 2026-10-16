# matplotlib/seaborn → Plotly mapping + traps

Constructs first, then the silent-behavior traps that shift numbers or drop data during translation.

## Principle: translate INTENT, not spines

When a construct has no faithful Plotly twin (stacked secondary axes, FuncFormatter
tick relabeling, exotic locators), reproduce what the READER EXTRACTS from it in
Plotly's native idiom — usually hover. A stacked date-ruler answering "what calendar
date is offset +20 on series #3" becomes `customdata` per trace + a `hovertemplate`;
a third y-axis mapping the shared curve onto another instrument's price scale
becomes hover fields or a toggle, not three spines. Such substitutions are
presentation-boundary changes: allowed, but each gets a ledger entry naming what was
dropped and what replaced it. Replicating spines pixel-for-pixel where Plotly fights
you produces a worse page than translating the intent — and hides the substitution
the ledger exists to surface.

## Construct map

| Notebook construct | Plotly equivalent | Notes |
|---|---|---|
| `ax.plot(x, y)` | `go.Scatter(mode="lines")` | |
| `ax.twinx()` | `make_subplots(specs=[[{"secondary_y": True}]])` + `secondary_y=True` per trace | axis ranges no longer auto-shared |
| `plt.subplots(r, c)` | `make_subplots(rows, cols)` — or the host app's grid factory (per-subplot legends) | |
| `ax.bar` / stacked | `go.Bar` + `barmode="stack"\|"group"\|"overlay"` | mpl stacks via bottom=; plotly via barmode |
| `ax.fill_between` | two `go.Scatter` traces + `fill="tonexty"` | order matters: lower trace first |
| `ax.axhline/axvline` | `fig.add_hline/add_vline` | |
| `ax.axhspan/axvspan` (shaded bands) | `fig.add_hrect/add_vrect` | layer="below" to keep traces on top |
| `ax.secondary_yaxis(pos, functions=(f, inv))` — incl. STACKS of them | `layout.yaxisN` with `overlaying="y", side="right"`, `position=`, `anchor="free"` — Plotly axes take no transform functions: precompute `tickvals` (in primary units) + `ticktext` (f(tickvals)) per ruler | >2 rulers: prefer intent translation (hover fields per scale) — see principle |
| `ax.secondary_xaxis` + `FuncFormatter` (tick relabeling, e.g. offsets→dates) | preferred: `customdata` + `hovertemplate` per trace; literal: `layout.xaxis2` with precomputed `tickvals/ticktext` | formatter logic must move into precomputed arrays — ledger the choice |
| `ax.annotate` / `ax.text` | `fig.add_annotation` | `arrowprops` → `showarrow=True` + `ax/ay` |
| `plt.suptitle` vs `ax.set_title` | `layout.title` vs `subplot_titles=` in make_subplots | distinct slots; don't merge them |
| line families faded by alpha (spaghetti/ensemble plots) | per-trace `opacity=` or rgba color | `legendgroup` + `showlegend` on one trace, else the legend explodes |
| `ax.set_yscale("log")` | `yaxis_type="log"` | log axes change perceived story — never drop |
| `plt.imshow` / `sns.heatmap` | `go.Heatmap` | mpl y-origin is TOP for imshow; plotly heatmap y ascends — `yaxis autorange="reversed"` to match |
| `sns.heatmap(annot=True)` | `go.Heatmap(text=..., texttemplate="%{text}")` | |
| `sns.lineplot(hue=...)` | one trace per group (groupby loop) | see estimator trap below |
| `sns.scatterplot(hue/size=...)` | `go.Scatter` per group, or `marker.size` array | |
| `sns.barplot` | `go.Bar` on PRE-AGGREGATED data | barplot aggregates internally — see trap |
| `sns.histplot` / `plt.hist` | `go.Histogram` | bin algorithms differ — pass explicit bins to both or precompute with np.histogram |
| `sns.kdeplot` | precompute with `scipy.stats.gaussian_kde` → `go.Scatter` | plotly has no native KDE |
| `sns.regplot` | scatter + manual `np.polyfit` line trace | compute the fit in the compute layer, parity-check the coefficients |
| `sns.boxplot/violinplot` | `go.Box` / `go.Violin` | whisker definitions differ (see trap) |
| `pd.DataFrame.plot(...)` | iterate columns → traces | `.plot()` hides a loop; make it explicit |
| color=`C0`,`tab10`, named / sns palettes | the SAME colors: `matplotlib.colors.to_hex(c)` → explicit `line.color` / `marker.color` | color is an encoding (per series, per point, per sign); Plotly's colorway cycles per TRACE, not per DataFrame, so an unset color scrambles the mapping. Host palette only where the notebook used defaults AND color carries no meaning — ledger it |
| `plt.xticks(rotation=45)` | `xaxis_tickangle=-45` | reserve `margin.b` for the rotated labels (`layout_policy(xtick_rotated=True)`) |
| dates on x (mpl auto-locator) | plotly handles natively | rangebreaks if the notebook hid weekends |
| `plt.figure(figsize=(w*ncols, h*nrows))` + `tight_layout()` / `bbox_inches="tight"` | `layout_policy(nrows, ncols, ...)` → `height`, `margin`, `vertical_spacing` | mpl grows the canvas and packs it for you; Plotly's height and margins are constants — compute them from rows/title lines once, in one shared function (`templates/layout_lint.py`) |
| `ax.legend(loc="best")` / `fig.legend(...)` outside | `layout.legend` from the policy (`"below"`/`"right"`), `legendgroup` + `showlegend` on one trace per series | a horizontal legend at `y≈1` lands on subplot titles; a vertical one at `x=1.02` needs `margin.r`; `lint_layout` flags both |
| `ax.set_title("name\nsub")` (two-line titles) | `subplot_titles=["name<br>sub"]` + `vertical_spacing` sized for the extra line | the next row's titles are annotations in the gap above it; too small a gap overprints the row above |

## Traps that change numbers or drop data

1. **mpl silently drops NaN in line plots** (gap in the line); Plotly also gaps by default (`connectgaps=False`) — but if the port added `.dropna()` to "clean up", the x-alignment between traces changed. Parity on arrays catches it.
2. **seaborn AGGREGATES inside the plot call.** `sns.lineplot`/`barplot` with repeated x values compute mean + 95% CI bootstrap by default. The notebook's line is NOT the raw data. Either reproduce (groupby mean in the compute layer + optional CI band) or consciously drop the CI with a ledger entry. Bootstrap CIs are UNSEEDED by default (`seed=None`) — the band differs on every run, so exact equality is impossible; pass `seed=`/`n_boot` when reproducing in the compute layer, else compare the band with tolerance and ledger it.
3. **Histogram bins:** mpl default 10 bins; plotly auto-bins differently; seaborn uses its own rules. Precompute `np.histogram` in the compute layer and hand both notebook and page the same bins, or pass explicit `bins=`/`xbins`.
4. **Box/violin internals:** whisker rule (1.5*IQR variants), outlier display, and KDE bandwidth differ across libs. If the notebook's exact quartiles matter, compute them in the compute layer and annotate.
5. **imshow orientation:** top-left origin vs plotly's bottom-left — a heatmap that "looks transposed/flipped" after port is this, not the data.
6. **twinx ranges:** mpl auto-scales each y independently around its data; after porting, plotly does too, but if the notebook manually set ylim on one axis, matching visuals requires porting those limits.
7. **Category order:** mpl/seaborn use appearance order or category dtype order; plotly sorts differently — pass `category_orders`/explicit tick arrays when the notebook's ordering carried meaning.
8. **`.plot()` sharex/stacked area defaults** (`df.plot.area` stacks by default) — verify stacking intent, don't assume.
9. **Date index frequency:** notebook may rely on matplotlib skipping missing dates visually while plotly draws a continuous time axis (weekend flatlines). `rangebreaks` or business-day reindex decision — ledger it.
10. **Colormaps for diverging data:** `sns.heatmap(cmap="RdBu_r")` does NOT center at 0 by default — it anchors to data min/max; centering only happens when the notebook passed `center=0`. Mirror that: `center=0` in the notebook → `zmid=0` in the plotly heatmap; no `center=` → do NOT add `zmid=0` (it would change the visual story in the name of fidelity).
