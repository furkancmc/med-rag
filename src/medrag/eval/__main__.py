"""Değerlendirme komutları.

Her `*_cli.py` modülü `register(subparsers)` ile kendi alt komutlarını ekler ve her alt komut
`func(args)` ayarlar. Yeni değerlendirme eklemek için bu dosyaya dokunmak gerekmez.
"""

import argparse
import importlib
import pkgutil

import medrag.eval as eval_pkg


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.eval")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for info in sorted(pkgutil.iter_modules(eval_pkg.__path__), key=lambda m: m.name):
        if info.name.endswith("_cli"):
            importlib.import_module(f"{eval_pkg.__name__}.{info.name}").register(sub)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
