"""Prevent importing first-generation application code in the clean V2 app."""
import importlib.abc
import sys


class NoLegacyApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'gamelens' or fullname.startswith('gamelens.'):
            raise ImportError('Babelander 2 must not import first-generation application bytecode')


def prepare():
    if not any(isinstance(f, NoLegacyApplication) for f in sys.meta_path):
        sys.meta_path.insert(0, NoLegacyApplication())
