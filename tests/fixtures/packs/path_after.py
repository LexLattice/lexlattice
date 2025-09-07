from pathlib import Path
def join(base, name):
    return Path(base).joinpath(name)
