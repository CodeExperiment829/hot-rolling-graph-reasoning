"""Install the public dependencies for the ReSched and GTool comparisons."""
import hashlib
import io
import os
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4
from zipfile import ZipFile


RUNTIME = Path(__file__).resolve().parent / ".benchmark-runtime"
REVISION = "4d1fda8ab4d78d1cd9664de28f3f77d88620f309"
RESCHED = f"https://raw.githubusercontent.com/XiangjieXiao/ReSched/{REVISION}/"
SUPPLEMENT = (
    "https://proceedings.iclr.cc/paper_files/paper/2026/file/"
    "715cf37ace0cb884530ab593eea6a50c-Supplemental-Conference.zip"
)
RESOURCES = {
    "SchedulingModel.py": (
        RESCHED + "PPO/SchedulingModel.py",
        None,
        "7af48a37c18a9df79392d73ef767044c20b2c756a2f37a7af2efbc39cfb1574f",
    ),
    "SD1-10x05.pth": (
        RESCHED + "ckpt/PPO/SD1-10x05.pth",
        None,
        "4efe1cd0927ec96b33622a5b409d9aecff767d736683989ca6bb9d6bd83fc61c",
    ),
    "gtool_multimedia.jsonl": (
        SUPPLEMENT,
        "GTool/dataset/multimedia/data.json",
        "acca69f0db70d065bb042b20e06f3822fd3ed2384e7f71763f44c9692c5fb2ae",
    ),
}


def resource(name):
    """Return a verified dependency, or None when it has not been installed."""
    path = RUNTIME / name
    if not path.exists():
        return None
    if hashlib.sha256(path.read_bytes()).hexdigest() != RESOURCES[name][2]:
        raise ValueError(f"Unexpected upstream release content for {name}")
    return path


def install():
    RUNTIME.mkdir(exist_ok=True)
    for name, (url, member, digest) in RESOURCES.items():
        if resource(name) is not None:
            continue
        with urlopen(url, timeout=120) as response:
            payload = response.read()
        if member:
            with ZipFile(io.BytesIO(payload)) as archive:
                payload = archive.read(member)
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError(f"Upstream integrity verification failed for {name}")
        temporary = RUNTIME / uuid4().hex
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, RUNTIME / name)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Installed {name}")


if __name__ == "__main__":
    install()
