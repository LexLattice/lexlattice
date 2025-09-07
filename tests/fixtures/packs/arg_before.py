# ruff: noqa: I001
import argparse
MODES = ['fast', 'slow']
def build():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', type=str)
    return p
