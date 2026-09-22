"""Stamp a fresh ?v=<timestamp> on every local module import in site/ so browsers never keep an
old script after a deploy (site/_headers also marks scripts no-cache; this is belt and braces).

    python scripts/stamp_site.py
Run by deploy.cmd before publishing.
"""
import os
import re
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(BASE, "site")
V = time.strftime("%Y%m%d%H%M")
PAT = re.compile(r"(from\s+['\"])(\./(?:js/)?[A-Za-z0-9_-]+\.js)(?:\?v=\d+)?(['\"])")


def stamp(path):
    s = open(path, encoding="utf-8").read()
    n, count = PAT.subn(lambda m: f"{m.group(1)}{m.group(2)}?v={V}{m.group(3)}", s)
    if count:
        open(path, "w", encoding="utf-8").write(n)
    return count


def main():
    total = 0
    for name in ("index.html", "backtest-live.html"):
        total += stamp(os.path.join(SITE, name))
    for name in os.listdir(os.path.join(SITE, "js")):
        if name.endswith(".js"):
            total += stamp(os.path.join(SITE, "js", name))
    print(f"stamped {total} imports with v={V}")


if __name__ == "__main__":
    main()
