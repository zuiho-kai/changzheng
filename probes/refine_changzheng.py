"""Character-specific layer-order and idle-motion corrections, preserving original artwork."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.reference/image2live2d-research/src'))
from image2live2d.core.decompose import from_psd
from image2live2d.pipeline import rig_from_stack
from image2live2d.backends.live2d.moc3_emit import build_atlas, rig_to_moc3
from image2live2d.backends.live2d.moc3_binary import write_moc3


def main():
    work = ROOT / 'artifacts/runtime-changzheng-v2'
    work.mkdir(exist_ok=True)
    source = ROOT / 'web/models/changzheng'
    out = work / 'bundle'
    shutil.copytree(source, out, dirs_exist_ok=True)
    stack = from_psd(ROOT / 'artifacts/changzheng-layered.psd', work / 'layers')
    rig = rig_from_stack(stack, name='model', source='changzheng-layered.psd')
    parts = {part.id: part for part in rig.parts}
    # The decomposer painted a skin strip onto the blouse's lower edge. The skirt
    # already extends behind that strip: correct occlusion instead of repainting it.
    for part in rig.parts:
        part.draw_order *= 2
    parts['05_clothing'].draw_order = parts['07_clothing'].draw_order + 1
    atlas, uv = build_atlas(rig, work / 'layers')
    atlas.save(out / 'textures/atlas.png')
    (out / 'model.moc3').write_bytes(write_moc3(rig_to_moc3(rig, atlas_uv=uv)))

    # Smooth twelve-second idle with restrained head movement; non-uniform blink
    # intervals avoid the original clockwork blink every 2.5 seconds.
    duration = 12
    curves = []
    blink = [(0, 1), (3.1, 1), (3.19, 0), (3.24, 0), (3.40, 1),
             (7.8, 1), (7.89, 0), (7.94, 0), (8.10, 1), (12, 1)]
    for key in ['ParamEyeLOpen', 'ParamEyeROpen']:
        segments = list(blink[0])
        for t, value in blink[1:]:
            segments.extend([0, t, value])
        curves.append({'Target': 'Parameter', 'Id': key, 'Segments': segments})
    import math
    for key, amplitude, baseline in [('ParamAngleX', 2.8, 0), ('ParamAngleY', 1.1, 0),
                                     ('ParamAngleZ', 1.0, 0), ('ParamBodyAngleX', .6, 0),
                                     ('ParamBreath', .12, .12)]:
        segments = [0, baseline]
        for i in range(1, 121):
            segments.extend([0, i / 10, baseline + amplitude * math.sin(2 * math.pi * i / 120)])
        curves.append({'Target': 'Parameter', 'Id': key, 'Segments': segments})
    counts = [(len(c['Segments']) - 2) // 3 for c in curves]
    idle = {'Version': 3, 'Meta': {'Duration': duration, 'Fps': 30, 'Loop': True,
        'AreBeziersRestricted': True, 'CurveCount': len(curves),
        'TotalSegmentCount': sum(counts), 'TotalPointCount': sum(n + 1 for n in counts),
        'UserDataCount': 0, 'UserDataSize': 0}, 'Curves': curves}
    (out / 'model.idle.motion3.json').write_text(json.dumps(idle), encoding='utf-8')
    report = {'parts': len(rig.parts), 'parameters': len(rig.parameters),
              'skirt_order': parts['05_clothing'].draw_order,
              'blouse_order': parts['07_clothing'].draw_order, 'idle_seconds': duration}
    (work / 'build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
