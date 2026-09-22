@echo off
REM Refresh the signals (with a reference committee run from the local .env key) and
REM publish the static site to Cloudflare Pages. Requires a one-time `npx wrangler login`.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python scripts\build_signals.py --reference || exit /b 1
copy /y docs\protofin-pipeline.html site\protofin-pipeline.html >nul
if exist research\out\backtest_report.html copy /y research\out\backtest_report.html site\backtest.html >nul
python scripts\stamp_site.py
npx wrangler pages deploy site --project-name protofin --branch main --commit-dirty=true
