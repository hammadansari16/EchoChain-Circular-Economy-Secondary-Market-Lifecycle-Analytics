"""
Shared path config for EchoChain scripts.

Everything is resolved relative to this file's own folder, so the whole
`echochain/` directory can be moved or copied anywhere (your laptop, a repo,
a different machine) and the scripts keep working with no edits.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
DB_PATH = os.path.join(BASE_DIR, "echochain.db")

os.makedirs(OUTPUT_DIR, exist_ok=True)
