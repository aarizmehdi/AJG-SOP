"""Install the pinned public E5 tokenizer at build time, never SOP/model data."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

REVISION = "3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3"
SHA256 = "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626"
URL = f"https://huggingface.co/intfloat/multilingual-e5-large/resolve/{REVISION}/tokenizer.json"


def install(output: Path) -> None:
    if output.exists() and hashlib.sha256(output.read_bytes()).hexdigest() == SHA256:
        return
    with urlopen(URL, timeout=90) as response:
        data = response.read(20_000_001)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("E5 tokenizer checksum mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    install(parser.parse_args().output)
