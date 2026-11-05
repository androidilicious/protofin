# Research website

The main navigation now follows the research contribution rather than the order
in which prototype versions were created:

- `dist/index.html`: research question, framework contribution, completed studies,
  headline findings, and explicit remaining work.
- `dist/framework.html`: model mechanics, a selectable saved monthly walkthrough,
  historical timing, controlled comparisons, forecast and
  portfolio evaluation, reliability checks, sources and limitations. The corrected
  one-month reference model is an expandable case study here.
- `dist/research.html`: added-signals experiment with the original wider-input
  exploratory results and a separate corrected-model development rerun.
- `dist/models.html`: forecasting-method experiment, with its own matched sample
  and compact information set. This shares the Experiments & results main tab.
- `dist/horizons.html`: corrected-model development extension for three- and
  six-month cumulative return targets. Forecast scoring allows overlapping targets;
  portfolio results use non-overlapping full-horizon holdings. A rolling 12-month
  evaluation window remains a diagnostic window, not a 12-month forecast.
- `dist/mvp.html`: a static overview of the earlier demonstration. Original HTML
  is preserved in `templates/original-mvp.html`; the older detailed files remain
  in `dist/previous/`. Their interactive data bundles are absent from this checkout,
  so the current navigation does not link to those broken replays.

The added-signal study has 44 common portfolio months; the estimator comparison
has 43. They must not be pooled into a single ranking. The corrected signal rerun
has its own recorded specification and preserves the original results. This
presentation change does not alter the frozen primary or reserved-period status.

## Build

Edit page content in `templates/`. `scripts/build-site.mjs` assembles the pages
and shared navigation. Browser behavior/styles remain in `dist/*.js` and `dist/*.css`.
The static MVP archive is built from `templates/archive-main.html`.

```sh
node site/scripts/build-site.mjs
node site/scripts/build-corrected-signals.mjs
node site/scripts/build-horizons.mjs
node site/scripts/test-research-site.mjs
node site/scripts/test-model-walkthrough.mjs
node site/scripts/test-research-stability.mjs
node site/scripts/test-model-comparison.mjs
```

Run from `deterministic_mvp`. The research and model-comparison builders also rebuild
the layout after refreshing their data bundles. They do not rerun forecasts.
Saved `research.html#primary`, `#stability` and `#research-method` links redirect
to their new framework locations; reference-model details open automatically.

To preview:

```sh
python3 -m http.server 4174 --bind 127.0.0.1 --directory site/dist
```

Run `python3 src/forecast_horizons.py` before `node site/scripts/build-horizons.mjs`
to regenerate the longer-target artifact. Upload the **contents** of `site/dist` for publication. Python sources and input
workbooks are not part of the static-site upload.
