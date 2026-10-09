"""Source launcher for the same bundled longevity test."""
from bootstrap import prepare
prepare()
from babelander.soaktest import run
if __name__ == '__main__': raise SystemExit(run())
