"""Non-interactive JSON CLI; native project formats remain authoritative."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "engines.json").read_text())


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class EngineError(Exception):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get("message", "Native engine failed"))


def run(command, cwd=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", shell=False)
    parsed = None
    for content in (result.stdout, result.stderr):
        try:
            parsed = json.loads(content)
            break
        except ValueError:
            pass
    if result.returncode:
        raise EngineError({"status": "engine_failed", "exitCode": result.returncode,
                           "native": parsed, "message": (result.stderr or result.stdout)[-12000:]})
    return parsed if parsed is not None else {"stdout": result.stdout.strip()}


def config_path(args):
    return Path(args.config or os.environ.get("CZ_IMG2LIVE2D_CONFIG",
                str(Path.home() / ".cz-img2live2d" / "config.json"))).resolve()


def engine(config, name):
    value = config.get(name)
    if not value:
        raise ValueError(f"Engine {name} is not configured; use configure --{name} ROOT")
    root = Path(value).resolve()
    if not (root / LOCK[name]["entry"]).is_file():
        raise ValueError(f"Engine {name} is not ready: {root / LOCK[name]['entry']}")
    return root


def identity(config, name):
    root = engine(config, name)
    head = run(["git", "-C", root, "rev-parse", "HEAD"])["stdout"]
    return {"root": str(root), "commit": head, "expectedCommit": LOCK[name]["commit"],
            "pinned": head == LOCK[name]["commit"], "entrySha256": digest(root / LOCK[name]["entry"])}


def project(args):
    root = Path(args.project).resolve()
    return root, read(root / "project.json")


def attach(root, data, path, kind):
    path = Path(path).resolve()
    token = digest(path)
    target = root / "source" / (token[:12] + path.suffix.lower())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    data[kind] = {"path": target.relative_to(root).as_posix(), "sha256": token}


def native(config, arguments):
    root = engine(config, "puppetloom")
    return run([config.get("node", "node"), root / LOCK["puppetloom"]["entry"], *arguments])


def latest(root, data, backend):
    record = data.get("builds", {}).get(backend)
    if not record:
        raise ValueError(f"Build {backend} first")
    return root / record["path"]


def execute(args):
    cp = config_path(args)
    config = read(cp) if cp.exists() else {}
    if args.command == "configure":
        for name in (*LOCK, "node", "cubism_vendor"):
            value = getattr(args, name, None)
            if value:
                config[name] = str(Path(value).resolve()) if name != "node" else value
        write(cp, config)
        return {"status": "configured", "config": str(cp), "engines": config}
    if args.command == "doctor":
        results = {}
        for name in LOCK:
            try:
                info = identity(config, name)
                results[name] = {"ready": info["pinned"], **info}
                if name == "puppetloom":
                    base = Path(info["root"])
                    results[name]["webRuntimeReady"] = (base / "packages/web-runtime/dist/puppetloom-web.js").is_file()
                    results[name]["cubismExporterConfigured"] = (base / "runtime/cubism-exporter/config.json").is_file()
            except (ValueError, OSError, EngineError) as error:
                results[name] = {"ready": False, "message": str(error), **LOCK[name]}
        return {"status": "ready" if all(x["ready"] for x in results.values()) else "needs_setup",
                "engines": results}
    if args.command == "native":
        arguments = args.arguments
        if arguments and arguments[0] == "--":
            arguments = arguments[1:]
        if not arguments:
            arguments = ["capabilities", "--json"]
        if "--json" not in arguments:
            arguments.append("--json")
        if args.project:
            root, data = project(args)
            arguments.extend(["--project", str(latest(root, data, "puppetloom"))])
        return {"backend": "puppetloom", "native": native(config, arguments)}
    if args.command == "init":
        root = Path(args.project).resolve()
        if root.exists():
            raise ValueError("Project directory already exists; use a new directory or assets")
        for source in (args.image, args.psd):
            if source and not Path(source).is_file():
                raise ValueError(f"Source file does not exist: {source}")
        data = {"version": 1, "builds": {}, "visualReview": "unreviewed"}
        if args.image:
            from PIL import Image
            with Image.open(args.image) as image:
                data["canvas"] = {"width": image.width, "height": image.height, "origin": "top-left", "yAxis": "down"}
        root.mkdir(parents=True)
        for name in ("image", "psd"):
            if getattr(args, name):
                attach(root, data, getattr(args, name), name)
        if "psd" not in data:
            request = {"status": "needs_assets", "input": data.get("image"), "canvas": data.get("canvas"),
                       "requestedArtifact": "aligned layered PSD", "agentAction": "Inspect source image and prepare only the parts supported by its artwork",
                       "suggestedParts": ["face", "front hair", "back hair", "eyewhite", "irides", "eyelash", "eyebrow", "mouth_open", "mouth_close", "neck", "topwear"],
                       "preserve": ["character identity", "original canvas coordinates", "overlap and layer order"],
                       "resumeCommand": "assets --project <this-project> --psd <prepared.psd>"}
            write(root / "asset-request.json", request)
        write(root / "project.json", data)
        return {"status": "ready" if "psd" in data else "needs_assets", "project": str(root),
                "assetRequest": str(root / "asset-request.json") if "psd" not in data else None,
                "next": "build --backend puppetloom/anime25d" if "psd" in data else
                "Agent: prepare aligned layered PSD, then assets --psd; or use the named changzheng preset"}
    root, data = project(args)
    if args.command == "assets":
        if args.psd:
            attach(root, data, args.psd, "psd")
            if (root / "asset-request.json").exists():
                request = read(root / "asset-request.json")
                write(root / "asset-request.json", {**request, "status": "assets_attached", "supplied": data["psd"]})
        if args.changzheng:
            source = Path(args.changzheng).resolve()
            names = ("source.png", "blank.png", "expression.png", "surprised.png")
            from PIL import Image
            for name in names:
                with Image.open(source / name) as image:
                    if image.size != (1254, 1254):
                        raise ValueError("changzheng preset requires the aligned 1254x1254 asset set")
            destination = root / "source" / ("changzheng-" + uuid.uuid4().hex[:10])
            destination.mkdir(parents=True)
            for name in names:
                shutil.copy2(source / name, destination / name)
            data["changzheng"] = destination.relative_to(root).as_posix()
        write(root / "project.json", data)
        return {"status": "assets_attached", "project": str(root)}
    if args.command == "inspect":
        result = {"project": str(root), **data}
        if args.backend == "puppetloom":
            result["native"] = native(config, ["inspect", "--input", str(root / data["psd"]["path"]), "--json"])
        return result
    if args.command == "bridge":
        source_build = latest(root, data, "anime25d")
        prepared = source_build / "puppetloom-base.psd"
        if not prepared.exists():
            raise ValueError("Rebuild anime25d to produce the painted-layer interchange")
        destination = root / "builds" / ("puppetloom-" + uuid.uuid4().hex[:12])
        result = native(config, ["create", "--input", str(prepared), "--output", str(destination), "--seed", "42", "--json"])
        # Register the original open-mouth art through PuppetLoom's supported supplement API.
        painted = read(source_build / "layers.json")
        opened = next((p for p in painted["layers"] if p["name"] == "mouth_open"), None)
        supplement_result = None
        if opened:
            from PIL import Image
            full = Image.new("RGBA", (painted["canvas"]["w"], painted["canvas"]["h"]))
            tile = Image.frombytes("RGBA", (opened["width"], opened["height"]), (source_build / opened["file"]).read_bytes())
            full.paste(tile, (opened["x"], opened["y"]))
            supplements = destination / "cz-supplements"
            supplements.mkdir()
            count = 0
            for request in read(destination / "requests/asset-requests.json")["requests"]:
                if request["kind"] == "mouth-shape" and request.get("variant") == "open":
                    crop = request["crop"]
                    full.crop((crop["x"], crop["y"], crop["x"]+crop["width"], crop["y"]+crop["height"])).save(supplements / Path(request["output"]["path"]).name)
                    count += 1
            if count:
                supplement_result = native(config, ["enhance", "--project", str(destination), "--assets", str(supplements), "--json"])
                if supplement_result.get("rejected"):
                    raise EngineError({"status": "needs_assets", "message": "PuppetLoom rejected transferred mouth art", "native": supplement_result, "output": str(destination)})
        result = {"create": result, "enhance": supplement_result,
                  "verify": native(config, ["verify", "--project", str(destination), "--json"])}
        record = {"path": destination.relative_to(root).as_posix(), "provenance": identity(config, "puppetloom"),
                  "result": result, "visualReview": "unreviewed", "bridgedFrom": data["builds"]["anime25d"],
                  "interchangeSha256": digest(prepared), "transfer": "aligned painted layers only; PuppetLoom rebuilds its own rig"}
        write(destination / "cz-build.json", record)
        data["builds"]["puppetloom"] = record
        write(root / "project.json", data)
        return {"status": "awaiting_visual_review", "output": str(destination), "native": result,
                "transfer": record["transfer"]}
    if args.command == "tune":
        previous = latest(root, data, "anime25d")
        settings = run([config.get("node", "node"), HERE / "tune.cjs", engine(config, "anime25d"), previous, Path(args.settings).resolve()])
        destination = root / "builds" / ("anime25d-" + uuid.uuid4().hex[:12])
        shutil.copytree(previous, destination)
        write(destination / "settings.json", settings)
        record = {**data["builds"]["anime25d"], "path": destination.relative_to(root).as_posix(),
                  "previousBuild": previous.relative_to(root).as_posix(), "settingsSha256": digest(destination / "settings.json"), "visualReview": "unreviewed"}
        write(destination / "cz-build.json", record)
        data["builds"]["anime25d"] = record
        write(root / "project.json", data)
        return {"status": "awaiting_visual_review", "output": str(destination), "settings": str(destination / "settings.json")}
    if args.command == "build":
        backend = args.backend
        if backend != "changzheng" and "psd" not in data:
            raise ValueError("needs_assets: attach a layered PSD first")
        if backend == "changzheng" and "changzheng" not in data:
            raise ValueError("needs_assets: assets --changzheng ALIGNED_DIRECTORY")
        destination = root / "builds" / (backend + "-" + uuid.uuid4().hex[:12])
        destination.parent.mkdir(exist_ok=True)
        dependency = "moc3" if backend == "changzheng" else backend
        provenance = identity(config, dependency)
        if not provenance["pinned"]:
            raise ValueError(f"Engine revision differs from engines.json: {provenance['commit']}")
        if backend == "puppetloom":
            result = native(config, ["create", "--input", str(root / data["psd"]["path"]),
                                      "--output", str(destination), "--seed", "42", "--json"])
        elif backend == "anime25d":
            result = run([config.get("node", "node"), HERE / "anime.cjs", engine(config, backend),
                          root / data["psd"]["path"], destination])
        else:
            result = run([sys.executable, HERE / "changzheng.py", "--assets", root / data["changzheng"],
                          "--output", destination, "--moc3-root", engine(config, "moc3")])
        record = {"path": destination.relative_to(root).as_posix(), "provenance": provenance,
                  "result": result, "visualReview": "unreviewed"}
        write(destination / "cz-build.json", record)
        data["builds"][backend] = record
        data["visualReview"] = "unreviewed"
        write(root / "project.json", data)
        return {"status": "awaiting_visual_review", "backend": backend, "output": str(destination), "native": result}
    build = latest(root, data, args.backend)
    if args.command == "export":
        destination = Path(args.output).resolve()
        if destination.exists():
            raise ValueError("Export requires a new destination")
        if args.format == "cubism" and args.backend == "anime25d":
            raise ValueError("Anime2.5DRig does not emit Cubism; use PuppetLoom exporter or Changzheng")
        destination.mkdir(parents=True)
        model_output = destination / "model"
        if args.backend == "puppetloom":
            verb = ["cubism", "export"] if args.format == "cubism" else ["export"]
            result = native(config, [*verb, "--project", str(build), "--output", str(model_output), "--json"])
        else:
            shutil.copytree(build, model_output)
            result = {"output": str(model_output), "format": "moc3" if args.backend == "changzheng" else "anime25d"}
        shutil.copytree(root / "source", destination / "source")
        record = {**data["builds"][args.backend], "path": "model", "exportedFrom": str(build)}
        exported = {**data, "builds": {args.backend: record}}
        write(model_output / "cz-build.json", record)
        write(destination / "project.json", exported)
        if args.backend == "changzheng":
            runtime = destination / "runtime"
            runtime.mkdir()
            for name in ("avatar-performance.js", "secondary-motion.js", "ANIME25D-LICENSE.txt", "changzheng-provenance.json"):
                shutil.copy2(HERE / name, runtime / name)
        return {"status": "exported", "output": str(destination), "visualReview": "unreviewed", "native": result}
    if args.command == "review":
        if args.backend == "puppetloom" and args.native_sheet:
            destination = root / "reviews" / ("puppetloom-" + uuid.uuid4().hex[:10])
            return {"status": "awaiting_visual_review", "native": native(config, ["render", "--project", str(build),
                    "--output", str(destination), "--suite", "calibration", "--size", "960", "--focus", "whole", "--json"])}
        from .review import review
        return review(root, data, build, args, config)
    raise ValueError("Unsupported command")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Explicit machine-local engine config")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("configure")
    for name in LOCK:
        setup.add_argument("--" + name)
    setup.add_argument("--node")
    setup.add_argument("--cubism-vendor", dest="cubism_vendor")
    commands.add_parser("doctor")
    n = commands.add_parser("native", help="Full PuppetLoom CLI, arguments after --")
    n.add_argument("--project", help="Resolve unified project to its current PuppetLoom revision")
    n.add_argument("arguments", nargs=argparse.REMAINDER)
    for command in ("init", "assets", "inspect", "build", "bridge", "tune", "review", "export"):
        p = commands.add_parser(command)
        p.add_argument("--project", required=True)
        if command == "tune":
            p.add_argument("--settings", required=True)
        if command == "init":
            p.add_argument("--image")
            p.add_argument("--psd")
        if command == "assets":
            p.add_argument("--psd")
            p.add_argument("--changzheng")
        if command in ("build", "review", "export", "inspect"):
            p.add_argument("--backend", choices=("puppetloom", "anime25d", "changzheng"),
                           required=command != "inspect")
        if command == "review":
            p.add_argument("--workspace", help="Isolated simulator/workspace directory", required=False)
            p.add_argument("--seconds", type=int, default=30)
            p.add_argument("--base-url", default="http://127.0.0.1:17874/static")
            p.add_argument("--audio", help="Existing audio clip for actual PCM-driven lip sync")
            p.add_argument("--native-sheet", action="store_true", help="PuppetLoom native calibration sheet")
        if command == "export":
            p.add_argument("--output", required=True)
            p.add_argument("--format", choices=("native", "cubism"), default="native")
    args = parser.parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False))
    except EngineError as error:
        print(json.dumps(error.result, ensure_ascii=False))
        sys.exit(3)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        sys.exit(2)
