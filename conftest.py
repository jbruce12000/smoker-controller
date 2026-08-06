import os
import sys

# make `import config` (repo root) and `import oven` (lib/) resolvable from tests
_root = os.path.dirname(os.path.abspath(__file__))
for path in (_root, os.path.join(_root, 'lib')):
    if path not in sys.path:
        sys.path.insert(0, path)
