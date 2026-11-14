"""Compatibility entry point; the maintained updater lives in scripts/sync.py."""
from pathlib import Path
import runpy
import sys
scripts = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(scripts))
if __name__ == '__main__':
    runpy.run_path(str(scripts / 'sync.py'), run_name='__main__')
