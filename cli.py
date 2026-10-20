"""Command-line order dissect (handy for testing / batch use).

Usage:  py cli.py 10-1234567 [more order refs...] [--keep-open] [--no-subcases] [--no-downloads]
Saves each order to <Documents>/SALTO Buddy/<order> - <STC>/ including <order>.xlsx.
"""
import os
import sys

from salto import config
from salto.actions import order_lookup
from salto.browser import SaltoBrowser
from salto.case import Options
from salto.export import export_report


def main(refs, flags):
    cfg = config.load()
    b = SaltoBrowser(log=lambda m: print(m, flush=True))
    try:
        for ref in refs:
            opts = Options(subcases="--no-subcases" not in flags, downloads="--no-downloads" not in flags)
            rep = order_lookup(b, ref, cfg["export_dir"], full=True, opts=opts)
            print(f"\nOrder {ref}: STC {rep.stc_id} | stage {rep.current_stage} | EQPs {', '.join(rep.eqps)}")
            if rep.case:
                print(f"  scope devices {len(rep.case.scope_devices)} | sub-cases {len(rep.case.subcases)}"
                      f" | participants {len(rep.case.participants)}")
            if rep.folder:
                print("  saved:", export_report(rep, os.path.join(rep.folder, f"{ref}.xlsx")))
    finally:
        if "--keep-open" not in flags:
            b.quit()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    main(args, [a for a in sys.argv[1:] if a.startswith("--")])
