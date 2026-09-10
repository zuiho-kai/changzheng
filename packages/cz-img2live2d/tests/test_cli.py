"""Public CLI regressions; live renderer acceptance is recorded separately."""
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image


def invoke(*args, cwd=None):
    process = subprocess.run([sys.executable, "-m", "cz_img2live2d", *map(str, args)],
                             cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return process.returncode, json.loads(process.stdout)


def test_image_project_is_needs_assets_and_portable(tmp_path):
    image = tmp_path / "character.png"
    Image.new("RGBA", (30, 50), "red").save(image)
    project = tmp_path / "角色 with spaces"
    code, result = invoke("init", "--image", image, "--project", project, cwd=tmp_path)
    assert code == 0 and result["status"] == "needs_assets"
    data = json.loads((project / "project.json").read_text())
    assert (project / data["image"]["path"]).read_bytes() == image.read_bytes()
    image.unlink()
    assert invoke("inspect", "--project", project, cwd=tmp_path)[0] == 0


def test_existing_project_is_preserved(tmp_path):
    project = tmp_path / "character"
    invoke("init", "--project", project)
    before = (project / "project.json").read_bytes()
    code, result = invoke("init", "--project", project)
    assert code == 2 and result["status"] == "error"
    assert (project / "project.json").read_bytes() == before


def test_missing_engine_does_not_publish_a_build(tmp_path):
    project = tmp_path / "character"
    fake_psd = tmp_path / "source.psd"
    fake_psd.write_bytes(b"not a psd")
    invoke("init", "--project", project, "--psd", fake_psd)
    before = (project / "project.json").read_bytes()
    code, result = invoke("--config", tmp_path / "no-engines.json", "build", "--project", project, "--backend", "puppetloom")
    assert code == 2 and result["status"] == "error"
    assert (project / "project.json").read_bytes() == before


def test_native_failure_is_json_with_exit_code(tmp_path):
    from cz_img2live2d.cli import run, EngineError
    try:
        run([sys.executable, "-c", 'import sys;sys.stderr.write("native rejected input");sys.exit(7)'])
    except EngineError as error:
        assert error.result["exitCode"] == 7
        assert "native rejected input" in error.result["message"]
    else:
        raise AssertionError("Native error was swallowed")


def test_export_refuses_existing_directory(tmp_path):
    project = tmp_path / "character"
    invoke("init", "--project", project)
    data = json.loads((project / "project.json").read_text())
    data["builds"]["changzheng"] = {"path": "old-build"}
    (project / "project.json").write_text(json.dumps(data))
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("user content")
    code, _ = invoke("export", "--project", project, "--backend", "changzheng", "--output", output)
    assert code == 2 and marker.read_text() == "user content"


def test_anime_cannot_mislabel_cubism_export(tmp_path):
    project = tmp_path / "character"
    invoke("init", "--project", project)
    data = json.loads((project / "project.json").read_text())
    data["builds"]["anime25d"] = {"path": "old-build"}
    (project / "project.json").write_text(json.dumps(data))
    output = tmp_path / "unsupported"
    code, result = invoke("export", "--project", project, "--backend", "anime25d", "--format", "cubism", "--output", output)
    assert code == 2 and "does not emit Cubism" in result["message"]
    assert not output.exists()
