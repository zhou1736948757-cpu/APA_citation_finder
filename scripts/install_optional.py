"""APA_citation_finder :: install_optional.py
One-command installer for the OPTIONAL sources (Exa / Google Scholar /
local PDF). Core flow never needs these; this script exists so
enabling an optional source is a single step instead of a hunt through
docs. Safe to re-run: pip is idempotent.

Usage:
  python install_optional.py            # install everything optional
  python install_optional.py --check    # report what is installed/missing
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REQ = Path(__file__).resolve().parent.parent / "requirements-optional.txt"
TOOLS = Path(__file__).resolve().parent.parent / "tools" / "pop8query"

# module name -> (pip package, what it enables)
OPTIONAL = [
    ("exa_py", "exa-py", "Exa 语义检索 (search_exa.py) — 需 EXA_API_KEY"),
    ("scholarly", "scholarly", "Google Scholar (search_google_scholar.py) — 可能被反爬限制"),
    ("fitz", "PyMuPDF", "本地 PDF 元数据/全文提取 (search_local.py)"),
]


def _installed(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def _pop_installed() -> bool:
    return TOOLS.exists() or shutil.which("pop8query") is not None


def check() -> int:
    print("可选源依赖状态：")
    missing = 0
    for mod, pkg, what in OPTIONAL:
        ok = _installed(mod)
        print(f"  [{'OK ' if ok else 'MISS'}] {pkg:12s} {what}")
        missing += 0 if ok else 1
    pop_ok = _pop_installed()
    print(f"  [{'OK ' if pop_ok else 'MISS'}] pop8query    Publish-or-Perish CLI (search_pop.py)")
    missing += 0 if pop_ok else 1
    if missing:
        print(f"\n{missing} 个缺失。安装：python scripts/install_optional.py")
    else:
        print("\n全部可选依赖已就绪。")
    return 0


def install() -> int:
    if not REQ.exists():
        print(f"找不到 {REQ}", file=sys.stderr)
        return 1
    print(f"安装可选依赖（来自 {REQ.name}）…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REQ)])
    if r.returncode != 0:
        print("安装失败，请检查网络或 pip 源。", file=sys.stderr)
        return r.returncode
    print("\n完成。启用方式：")
    print("  Exa          : 设置环境变量 EXA_API_KEY 后调用 search_exa.py")
    print("  Google Scholar: 直接调用 search_google_scholar.py（可能被反爬限制）")
    print("  Local PDF    : search_local.py --dir ~/papers（自动提取元数据/全文）")
    print("  PoP CLI      : 已内置 tools/pop8query（或下载 pop8mactools.pkg 解包）")
    print("核心流（OpenAlex/S2/Crossref）不受任何影响。")
    return 0


def _cli() -> int:
    p = argparse.ArgumentParser(description="安装/检查 APA_citation_finder 可选源依赖")
    p.add_argument("--check", action="store_true", help="只检查不安装")
    args = p.parse_args()
    return check() if args.check else install()


if __name__ == "__main__":
    sys.exit(_cli())
