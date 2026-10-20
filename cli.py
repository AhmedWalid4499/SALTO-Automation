"""Command-line version of Order Lookup (handy for testing / batch use).

Usage:  py cli.py 10-1753747 [more order refs...]
"""
import os
import sys

from salto.actions import order_lookup
from salto.browser import SaltoBrowser


def main(refs):
    b = SaltoBrowser(log=lambda m: print(m, flush=True))
    shots = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    os.makedirs(shots, exist_ok=True)
    try:
        for ref in refs:
            rep = order_lookup(b, ref, os.path.join(shots, f"{ref}.png"))
            print(f"\nOrder {ref}")
            print(f"  STC ID        : {rep.stc_id}")
            print(f"  Stages        : " + " > ".join(f"{s.name}[{s.state}]" for s in rep.stages))
            print(f"  Current stage : {rep.current_stage}")
            print(f"  Status        : {rep.status}")
            print(f"  EQPs ({len(rep.eqps)})     : {', '.join(rep.eqps)}")
            print(f"  Screenshot    : {rep.screenshot}")
    finally:
        if "--keep-open" not in sys.argv:
            b.quit()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    main(args)
