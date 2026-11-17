"""Scoring-model registry. Every model version lives in models/<version>.json and is never edited after it is
published; changes go in a new version. models/CURRENT names the version the pipeline runs by default.
Run an older model with env MODEL=v1.0 (or any version file name).
"""
import os, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, 'models')

def current_version():
    return open(os.path.join(MODELS, 'CURRENT')).read().strip()

def load_model(version=None):
    v = version or os.environ.get('MODEL') or current_version()
    with open(os.path.join(MODELS, f'{v}.json')) as f:
        m = json.load(f)
    assert m['version'] == v, f'models/{v}.json says version {m["version"]}'
    return m
