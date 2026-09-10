"""Render original engines in an isolated, user-specified static workspace."""
import asyncio
from pathlib import Path
import shutil
import time
from urllib.request import urlopen
import uuid

from .cli import HERE, digest, engine, native, read, write


def stage(build, backend, destination, config):
    destination.mkdir(parents=True)
    if backend == "anime25d":
        upstream = engine(config, "anime25d")
        shutil.copytree(upstream / "lib", destination / "lib")
        for name in ("index.html", "LICENSE", "eye_close.psd", "mouth_close.psd"):
            shutil.copy2(upstream / name, destination / name)
        shutil.copy2(build / "source.psd", destination / "source.psd")
        if (build / "settings.json").exists():
            shutil.copy2(build / "settings.json", destination / "settings.json")
        else:
            write(destination / "settings.json", None)
        script = (destination / "lib/app.js").read_text(encoding="utf-8")
        marker = "const SAMPLE_FILES={A:'sample2.psd',B:'sample.psd'};"
        if marker not in script or not script.rstrip().endswith("})();"):
            raise ValueError("Upstream app bridge anchor changed; check pinned version")
        script = script.replace(marker, "const SAMPLE_FILES={A:'source.psd',B:'source.psd'};")
        script = script.rstrip()[:-5] + (HERE / "anime-bridge.js").read_text(encoding="utf-8") + "\n})();\n"
        (destination / "lib/app.js").write_text(script, encoding="utf-8")
    elif backend == "puppetloom":
        upstream = engine(config, backend)
        sdk = upstream / "packages/web-runtime/dist/puppetloom-web.js"
        if not sdk.exists():
            raise ValueError("Build PuppetLoom Web SDK: npm run build -w @puppetloom/web-runtime")
        # Native export bakes the exact current calibration/authoring revision.
        native(config, ["export", "--project", str(build), "--output", str(destination / "model"), "--json"])
        shutil.copy2(sdk, destination / sdk.name)
        shutil.copy2(upstream / "LICENSE", destination / "PUPPETLOOM-LICENSE.txt")
        shutil.copy2(HERE / "puppet-preview.html", destination / "index.html")
    else:
        shutil.copytree(build, destination / "model")
        vendor = Path(config.get("cubism_vendor", ""))
        names = ("pixi-6.5.10.min.js", "live2dcubismcore.min.js", "cubism4-0.4.0.min.js")
        if not all((vendor / name).is_file() for name in names):
            raise ValueError("Configure --cubism-vendor to a licensed Cubism/PIXI runtime directory")
        (destination / "vendor").mkdir()
        for name in names:
            shutil.copy2(vendor / name, destination / "vendor" / name)
        for file in vendor.glob("*LICENSE*"):
            shutil.copy2(file, destination / "vendor" / file.name)
        for name in ("avatar-performance.js", "secondary-motion.js", "ANIME25D-LICENSE.txt"):
            shutil.copy2(HERE / name, destination / name)
        shutil.copy2(HERE / "cubism-preview.html", destination / "index.html")


async def capture(url, output, seconds, has_audio):
    from playwright.async_api import async_playwright
    errors, samples = [], []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--autoplay-policy=no-user-gesture-required"])
        context = await browser.new_context(viewport={"width": 640, "height": 800},
                    record_video_dir=str(output / "raw"), record_video_size={"width": 640, "height": 800})
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        video = page.video
        try:
            await page.goto(url)
            await page.wait_for_function("window.cz?.ready || window.cz?.error", timeout=60000)
            error = await page.evaluate("window.cz.error")
            if error:
                raise ValueError(error)
            await page.evaluate("window.cz.setState('idle'); window.cz.mouth(0)")
            await page.screenshot(path=str(output / "neutral.png"))
            if has_audio:
                await page.evaluate("""async()=>{
                  const ctx=new AudioContext();await ctx.resume();
                  const buffer=await ctx.decodeAudioData(await (await fetch('audio.wav')).arrayBuffer());
                  window.audioProbe={ctx,buffer,source:null,analyser:ctx.createAnalyser(),active:false};
                  audioProbe.analyser.fftSize=512;audioProbe.analyser.connect(ctx.destination);
                  const values=new Float32Array(512);
                  window.startAudio=()=>{const p=audioProbe;p.source=ctx.createBufferSource();p.source.buffer=buffer;p.source.loop=true;p.source.connect(p.analyser);p.source.start();p.active=true;};
                  window.stopAudio=()=>{audioProbe.active=false;audioProbe.source?.stop();cz.mouth(0);};
                  setInterval(()=>{const p=audioProbe;if(!p.active)return;p.analyser.getFloatTimeDomainData(values);
                    cz.mouth(Math.min(1,Math.sqrt(values.reduce((a,b)=>a+b*b,0)/values.length)*7));},33);
                }""")
            start = time.monotonic()
            state = "idle"
            checkpoints = set()
            while time.monotonic() - start < seconds:
                elapsed = time.monotonic() - start
                fraction = elapsed / seconds
                desired = "idle" if fraction < .17 or fraction >= .8 else "listening" if fraction < .3 else "thinking" if fraction < .4 else "speaking"
                if desired != state:
                    await page.evaluate("s=>cz.setState(s)", desired)
                    if state == "speaking":
                        await page.evaluate("window.stopAudio ? stopAudio() : cz.mouth(0)")
                    if desired == "speaking" and has_audio:
                        await page.evaluate("startAudio()")
                    state = desired
                sample = await page.evaluate("cz.stats()")
                samples.append({"t": round(elapsed, 3), "state": state, **sample})
                mark = "speaking" if .55 < fraction < .7 else "stopped" if fraction >= .86 else None
                if mark and mark not in checkpoints:
                    await page.screenshot(path=str(output / (mark + ".png")))
                    checkpoints.add(mark)
                await asyncio.sleep(.1)
            settings = await page.evaluate("window.cz.settings ? cz.settings() : null")
            # Separate explicit poses from the PCM scenario; inspect painted mouth response.
            await page.evaluate("cz.setState('idle');cz.mouth(0)")
            await page.wait_for_timeout(150)
            await page.screenshot(path=str(output / "mouth-closed.png"))
            await page.evaluate("cz.mouth(1)")
            await page.wait_for_timeout(100)
            await page.screenshot(path=str(output / "mouth-open.png"))
            await page.evaluate("cz.mouth(0)")
            await page.screenshot(path=str(output / "final.png"))
        finally:
            await context.close()
            await video.save_as(str(output / "rehearsal.webm"))
            await browser.close()
    return {"samples": samples, "errors": errors, "settings": settings}


def review(root, data, build, args, config):
    if not args.workspace:
        raise ValueError("review requires --workspace pointing to an isolated served static directory")
    if not 3 <= args.seconds <= 120:
        raise ValueError("Review seconds must be between 3 and 120")
    with urlopen(args.base_url.rstrip("/") + "/index.html", timeout=5) as response:
        if response.status != 200:
            raise ValueError("Static workspace is not served")
    tag = args.backend + "-" + uuid.uuid4().hex[:10]
    destination = Path(args.workspace).resolve() / "cz-img2live2d" / tag
    output = root / "reviews" / tag
    output.mkdir(parents=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ignore = destination.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n!.gitignore\n", encoding="utf-8")
    stage(build, args.backend, destination, config)
    if args.audio:
        shutil.copy2(args.audio, destination / "audio.wav")
    snapshot = {p.relative_to(destination).as_posix(): digest(p) for p in destination.rglob("*") if p.is_file()}
    write(output / "snapshot.json", snapshot)
    url = args.base_url.rstrip("/") + "/cz-img2live2d/" + tag + "/index.html"
    if args.backend == "anime25d":
        url += "?obs=1"
    raw = asyncio.run(capture(url, output, args.seconds, bool(args.audio)))
    samples = raw.pop("samples")
    settings = raw.pop("settings")
    if settings is not None:
        write(output / "settings.json", settings)
    talking = [s["mouth"] for s in samples if s["state"] == "speaking"]
    stopped = [s["mouth"] for s in samples if s["t"] > args.seconds * .86]
    report = {"status": "awaiting_visual_review", "backend": args.backend, "sourceBuild": str(build),
              "buildManifestSha256": digest(build / "cz-build.json"), "url": url,
              "snapshotManifest": str(output / "snapshot.json"), "snapshotManifestSha256": digest(output / "snapshot.json"),
              "video": str(output / "rehearsal.webm"), "videoHasAudio": False,
              "actualPcmInput": bool(args.audio), "audioSha256": digest(args.audio) if args.audio else None,
              "durationSeconds": args.seconds, "visualReview": "unreviewed", **raw,
              "checks": {"noPageErrors": not raw["errors"], "mouthParameterMoves": max(talking, default=0) > .03 if args.audio else None,
                         "mouthParameterClosesAfterStop": max(stopped, default=1) < .01},
              "checkScope": "Runtime parameter response only; inspect rendered mouth and native capabilities separately.", "samples": samples}
    write(output / "report.json", report)
    return {k: v for k, v in report.items() if k != "samples"} | {"report": str(output / "report.json")}
