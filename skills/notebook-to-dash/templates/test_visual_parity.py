"""Template: VISUAL parity gate — Plotly twin vs the notebook's matplotlib helper.

Symmetric to test_parity.py (numbers). One row per notebook figure cell:
  - golden_fig_<cell>.json  = mpl_spec() of the NOTEBOOK helper on the frozen inputs
                              (harvest once in the notebook env; commit; never from the twin)
  - the twin is called with the cell's EXACT arguments
  - diff_spec() must return zero ERR; WARNs print for the ledger
  - a contact sheet PNG lands in artifacts/ for the fidelity walk

Regenerate goldens ONLY when the notebook figure itself changed:
    N2D_UPDATE_GOLDENS=1 <notebook-env-python> -m pytest tests/parity/test_visual_parity.py
(the notebook helper must be importable in that env; the gate itself needs only plotly).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# copy fig_spec.py and layout_lint.py from the skill's templates/ next to this file
from fig_spec import capture_mpl, diff_spec, mpl_spec, plotly_spec, save_spec, contact_sheet
from layout_lint import lint_layout

# --- CONFIG (adapt per conversion) -------------------------------------------
HERE = Path(__file__).parent
GOLDEN_DIR = HERE / "goldens"
ART_DIR = HERE / "artifacts"
# from myapp.plotting import finance_visual_plotly as fvp      # the twins
# import finance_visual as fv                                   # notebook helper (goldens only)
# DATA = <the frozen snapshot from Step 1, loaded ONCE per test (defensive copies)>

# One entry per notebook figure cell: (cell_id, helper_fn, twin_fn, args, kwargs)
# args/kwargs are the notebook cell's call, verbatim.
FIGURES = [
    # ("cell397", fv.plot_df_subplots, fvp.plot_df_subplots,
    #  ([DATA["commodity_cum"], DATA["im_suridx_z"], DATA["ex_suridx_z"], DATA["net_suridx_z"]],),
    #  dict(axis=["L1", "R1", "R1", "R1"], threshold_fill=[None, None, None, None],
    #       title_last_yymmdd=True, title=[...])),
]
# ------------------------------------------------------------------------------


@pytest.mark.parametrize("cell_id,helper_fn,twin_fn,args,kwargs", FIGURES, ids=[f[0] for f in FIGURES])
def test_figure_structure_matches(cell_id, helper_fn, twin_fn, args, kwargs):
    golden_path = GOLDEN_DIR / f"golden_fig_{cell_id}.json"
    mpl_fig = None
    if os.environ.get("N2D_UPDATE_GOLDENS") or not golden_path.exists():
        import matplotlib
        matplotlib.use("Agg")
        figs = capture_mpl(helper_fn, *args, **kwargs)
        assert len(figs) == 1, f"{cell_id}: helper produced {len(figs)} figures; split the entry per figure"
        mpl_fig = figs[0]
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        save_spec(mpl_spec(mpl_fig), golden_path)
    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    fig = twin_fn(*args, **kwargs)
    got = plotly_spec(fig)
    findings = diff_spec(golden, got) + lint_layout(fig)   # structure + geometry in one red/green
    warns = [m for m in findings if m.startswith("WARN")]
    errs = [m for m in findings if m.startswith("ERR")]
    if warns:
        print(f"\n[{cell_id}] WARN (judge, then ledger):\n  " + "\n  ".join(warns))
    if mpl_fig is not None:
        ART_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[{cell_id}] sheet: {contact_sheet(mpl_fig, fig, ART_DIR / f'{cell_id}_sheet.png')}")
        import matplotlib.pyplot as plt
        plt.close("all")
    assert not errs, f"[{cell_id}] visual parity:\n  " + "\n  ".join(errs)


def test_every_notebook_figure_is_listed():
    # Keep FIGURES honest: compare against the cell coverage map / plot_calls.py inventory.
    # e.g. inventory = json.loads((HERE / "plot_calls.json").read_text())["calls"]
    #      helper_cells = {c for k, v in inventory.items() if k.startswith("fv.") for c in v["cells"]}
    #      listed = {int(f[0].removeprefix("cell")) for f in FIGURES}
    #      assert helper_cells <= listed, f"figure cells without a visual gate: {sorted(helper_cells - listed)}"
    assert FIGURES, "FIGURES is empty: every notebook figure cell needs an entry (or a 'dropped' ledger line)"
