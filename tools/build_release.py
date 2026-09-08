"""Package only reviewed application files as a deterministic Python zipapp."""
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / "dist" / "runsignal.pyz"
target.parent.mkdir(parents=True, exist_ok=True)
files = {p.relative_to(root).as_posix(): p.read_bytes() for p in (root / "runsignal").iterdir()
         if p.is_file() and p.suffix in {".py", ".html"}}
files["__main__.py"] = b"from runsignal.__main__ import main\nraise SystemExit(main())\n"
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name, content in sorted(files.items()):
        info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, content)
checksum = hashlib.sha256(target.read_bytes()).hexdigest()
(target.parent / "SHA256SUMS").write_text(checksum + "  runsignal.pyz\n")
print(target)
print(checksum)
