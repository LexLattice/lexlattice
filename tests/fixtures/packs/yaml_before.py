# ruff: noqa: I001
import yaml

def loadit(s):
    return yaml.load(s)

def load_with_loader(s):
    return yaml.load(s, Loader=yaml.SafeLoader)
