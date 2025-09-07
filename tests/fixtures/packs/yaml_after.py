# ruff: noqa: I001
import yaml

def loadit(s):
    return yaml.safe_load(s)

def load_with_loader(s):
    return yaml.safe_load(s)
