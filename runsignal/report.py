import json
from importlib.resources import files


def render(data):
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return files("runsignal").joinpath("report.html").read_text(encoding="utf-8").replace("__RUNSIGNAL_DATA__", payload)
