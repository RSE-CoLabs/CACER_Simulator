
import os
import glob

# Prendi tutti i file .py nella cartella corrente (src), tranne __init__.py
modules = glob.glob(os.path.join(os.path.dirname(__file__), "*.py"))
modules = [os.path.basename(f)[:-3] for f in modules if not f.endswith("__init__.py")]

# Importa dinamicamente ogni modulo trovato
for module_name in modules:
    exec(f"from . import {module_name}")
