import os
from parser import do_parse

for root, dirs, files in os.walk("parse_all", topdown=False):
    for name in files:
        if name.endswith('config.json'):
            folder = os.path.dirname(os.path.join(root, name))
            metrics = os.path.join(folder, 'metrics/')
            print(f"Processando pasta: {folder}")
            do_parse(folder, metrics)