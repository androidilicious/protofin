"""Render research/out/backtest_report.html from the backtest CSV outputs.

    python research/backtest.py && python research/backtest_chart.py
"""
import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
# Validated categorical palette (light surface); fixed order, one hue per strategy.
COLORS = {"fixed_60_40": "#2a78d6", "prior_only": "#eb6834", "rate_shock_rule": "#1baf7a",
          "rate_shock_gated": "#eda100", "logged_llm": "#e87ba4", "logged_llm_gated": "#008300",
          "masked_llm": "#4a3aa7", "masked_llm_gated": "#e34948"}
LABELS = {"fixed_60_40": "Fixed 60/40", "prior_only": "Prior only + trade policy",
          "rate_shock_rule": "Rate-shock rule views", "rate_shock_gated": "Rule views, EPU/GPR gated",
          "logged_llm": "Logged LLM views", "logged_llm_gated": "Logged LLM views, gated",
          "masked_llm": "Masked LLM replay", "masked_llm_gated": "Masked LLM replay, gated"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e8e7e3"


def main():
    curves = pd.read_csv(os.path.join(OUT, "backtest_curves.csv"), index_col=0, parse_dates=True)
    weights = pd.read_csv(os.path.join(OUT, "backtest_weights.csv"), index_col=0, parse_dates=True)
    summary = pd.read_csv(os.path.join(OUT, "backtest_summary.csv"), index_col=0)
    indexed = curves / curves.iloc[0] * 100

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.62, 0.38],
                        subplot_titles=("Growth of 100, net of costs", "SPY weight, %"))
    for name in indexed.columns:
        c = COLORS[name]
        fig.add_trace(go.Scatter(x=indexed.index, y=indexed[name], name=LABELS[name],
                                 line=dict(color=c, width=2), legendgroup=name,
                                 hovertemplate="%{y:.1f}<extra>" + LABELS[name] + "</extra>"),
                      row=1, col=1)
        fig.add_trace(go.Scatter(x=weights.index, y=weights[name] * 100, name=LABELS[name],
                                 line=dict(color=c, width=2), legendgroup=name, showlegend=False,
                                 hovertemplate="%{y:.1f}%<extra>" + LABELS[name] + "</extra>"),
                      row=2, col=1)

    axis = dict(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=INK2, size=11))
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    fig.update_layout(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font=dict(color=INK, family="Inter, Segoe UI, sans-serif"),
        hovermode="x unified", height=760, margin=dict(l=60, r=30, t=110, b=40),
        legend=dict(orientation="h", y=1.06, yanchor="bottom", x=0, font=dict(color=INK2)),
        title=dict(text="Protofin allocation policy backtest", x=0, y=0.985, yanchor="top", font=dict(size=18)),
    )
    fig.update_xaxes(showspikes=True, spikemode="across", spikecolor=INK2, spikethickness=1, spikedash="dot")

    table = summary.rename(columns={"CAGR_%": "CAGR %", "Vol_%": "Vol %", "MaxDD_%": "Max DD %",
                                    "held_decisions": "held", "turnover_total_%": "turnover %",
                                    "cost_drag_total_%": "cost drag %", "avg_SPY_w_%": "avg SPY %",
                                    "views_available": "views"})
    table.index = [LABELS.get(i, i) for i in table.index]
    html_table = table.to_html(float_format=lambda v: f"{v:,.2f}", na_rep="", border=0,
                               classes="summary")
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Backtest Report</title>
<style>
 body{{background:{SURFACE};color:{INK};font-family:Inter,'Segoe UI',sans-serif;margin:0;padding:24px 16px;max-width:1200px;margin:auto}}
 table.summary{{border-collapse:collapse;font-size:13px;width:100%;margin-top:16px}}
 table.summary th,table.summary td{{padding:6px 10px;text-align:right;border-bottom:1px solid {GRID}}}
 table.summary th:first-child,table.summary td:first-child{{text-align:left}}
 table.summary th{{color:{INK2};font-weight:600}}
 p.note{{color:{INK2};font-size:12px;line-height:1.5}}
</style></head><body>
{fig.to_html(full_html=False, include_plotlyjs="cdn")}
<h3 style="margin-top:24px">Summary</h3>
{html_table}
<p class="note">All strategies share dates, prices, covariance windows, rebalance calendar and a flat one-way
transaction cost. "Prior only" and "Logged LLM views" run through the same allocation code as the live
dashboard. The rate-shock rule is a placeholder signal, not a validated one. Historical LLM views cannot be
backtested honestly here: there is no point-in-time news archive and the model has read the history it would
forecast. The logged-LLM line is a forward test that starts on the first live run and falls back to the prior
before that.</p>
</body></html>"""
    path = os.path.join(OUT, "backtest_report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("report ->", path)


if __name__ == "__main__":
    main()
