"""Hand-authored skin weights and facial meshes; uses only the upstream MOC3 serializer.

No automatic semantic rigging, landmarks, generated skeleton or low-resolution PSD.
Raster edits are imagegen outputs; this script extracts/keys/UV-packs those prepared assets.
"""
from pathlib import Path
import itertools
import json
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.reference/image2live2d-research/src'))
from image2live2d.backends.live2d.moc3_emit import EmitMesh, EmitParam, EmitPart, build_moc3
from image2live2d.backends.live2d.moc3_binary import write_moc3

WORK = ROOT / 'artifacts/runtime-manual-rig'
OUT = WORK / 'bundle'
SIZE = 1254


def smooth(a, b, x):
    t = max(0., min(1., (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def skin(x, y, values):
    """Continuous hand-painted equivalent weights: neck, head, shoulder and outer hair."""
    yaw, pitch, roll = (values.get(i, 0) / 30 for i in range(3))
    breath, hair = values.get(3, 0), values.get(4, 0)
    head = 1 - smooth(440, 585, y)
    outside = smooth(125, 225, abs(x - 646))
    head = max(head, outside * (1 - smooth(460, 1050, y)) * .65)
    angle = roll * math.radians(4)
    dx, dy = x - 646, y - 510
    rx = math.cos(angle) * dx - math.sin(angle) * dy - dx
    ry = math.sin(angle) * dx + math.cos(angle) * dy - dy
    # Yaw is a shallow ellipsoid projection, not a common translation of the
    # whole head. Central facial features sit forward of cheeks/hair, so the
    # far side compresses and the nose moves relative to the silhouette.
    theta = yaw * math.radians(16)
    radius = 220 - 105 * smooth(220, 475, y)
    cross_section = math.sqrt(max(0., 1 - (dx / radius) ** 2))
    depth = 115 * cross_section * smooth(20, 190, y) * (1-smooth(460,585,y))
    nx = x + head * (rx + dx * (math.cos(theta)-1) + depth * math.sin(theta))
    ny = y + head * (ry + 7 * pitch - dy * .012 * abs(pitch))
    # Breath translates the head with the shoulders; it never stretches facial features.
    ny -= 2.5 * breath * (1 - smooth(700, 1230, y))
    nx += (x - 646) * .0015 * breath * smooth(460, 700, y)
    nx += 3 * hair * outside * smooth(400, 900, y)
    return ((nx / SIZE - .5) * 2, (ny / SIZE - .5) * 2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    src, blank, expression = [Image.open(ROOT / 'artifacts/changzheng-manual-assets' / f'{s}.png').convert('RGB') for s in ('source', 'blank', 'expression')]
    assert all(im.size == (SIZE, SIZE) for im in (src, blank, expression))
    # Chroma-key the deliberately generated magenta background, preserving native pixels.
    rgb = np.asarray(blank, dtype=np.float32)
    spill = np.maximum(0, np.minimum(rgb[:, :, 0] - rgb[:, :, 1], rgb[:, :, 2] - rgb[:, :, 1]))
    alpha = np.clip((130 - spill) / 100, 0, 1)
    alpha[alpha < .03] = 0
    clean = np.clip((rgb - (1-alpha[:, :, None]) * np.array([255, 0, 255])) / np.maximum(alpha[:, :, None], .001), 0, 255)
    # The generated magenta backdrop is not perfectly uniform. Prevent its
    # residual green channel from tinting semi-transparent silver hair edges.
    edge = alpha < .98
    clean[:, :, 0][edge] = np.maximum(clean[:, :, 0][edge], clean[:, :, 1][edge] * .98)
    clean[:, :, 2][edge] = np.maximum(clean[:, :, 2][edge], clean[:, :, 1][edge] * .98)
    base = Image.fromarray(np.dstack([clean, alpha * 255]).astype('uint8'), 'RGBA')
    atlas = Image.new('RGBA', (2048, 2048))
    atlas.paste(base, (0, 0))
    params = [EmitParam(k, -30, 30, 0, [-30, 0, 30]) for k in ('ParamAngleX','ParamAngleY','ParamAngleZ')]
    params[0].keys = [-30, -15, 0, 15, 30]
    params += [EmitParam('ParamBreath', 0, 1, 0, [0, 1]), EmitParam('ParamHairSway', -1, 1, 0, [-1, 0, 1]),
               EmitParam('ParamEyeLOpen', 0, 1, 1, [0, .4, 1]), EmitParam('ParamEyeROpen', 0, 1, 1, [0, .4, 1]),
               EmitParam('ParamMouthOpenY', 0, 1, 0, [0, .25, 1])]
    meshes, parts, specs = [], [], []
    packed_x = 0

    def mesh(name, rect, placement, step, affect, kind='', control=None):
        x0,y0,x1,y1 = rect
        cols, rows = max(2, math.ceil((x1-x0)/step)), max(2, math.ceil((y1-y0)/step))
        points = [(x0+(x1-x0)*i/cols, y0+(y1-y0)*j/rows) for j in range(rows+1) for i in range(cols+1)]
        triangles = []
        for j in range(rows):
            for i in range(cols):
                a = j*(cols+1)+i
                triangles += [(a,a+1,a+cols+1),(a+1,a+cols+2,a+cols+1)]
        uv = [((placement[0]+x-x0)/2048,(placement[1]+y-y0)/2048) for x,y in points]
        keys, opacities = [], []
        # Cubism's first bound parameter is the fastest-changing keyform axis.
        for combo in itertools.product(*(params[i].keys for i in reversed(affect))):
            values = dict(zip(reversed(affect), combo)); v = values.get(control, 1)
            positions = []
            for x,y in points:
                if kind == 'eye_open': y = 355 + (y-355)*max(.06, v)
                if kind == 'mouth_open': y = 419 + (y-419)*(.08 + .92*v)
                positions.append(skin(x,y,values))
            opacity = 1.
            if kind == 'eye_open': opacity = min(1, v/.4)
            elif kind == 'eye_closed': opacity = max(0, 1-v/.4)
            elif kind == 'mouth_open': opacity = min(1, v/.25)
            elif kind == 'mouth_closed': opacity = max(0, 1-v/.25)
            keys.append(positions);opacities.append(opacity)
        parts.append(EmitPart(name, 100+len(parts)*10))
        meshes.append(EmitMesh(name,len(parts)-1,0,uv,triangles,affect,keys,opacities))
        specs.append({'id':name,'rect':rect,'vertices':len(points),'controls':[params[i].id for i in affect]})

    mesh('BodyHeadSkin', (0,0,SIZE,SIZE), (0,0), 28, [0,1,2,3,4])
    # Viewer-left/right feature coordinates picked directly from the full-resolution drawing.
    patches = [
        ('BrowLeft',src,(548,268,618,296),'',None), ('BrowRight',src,(678,268,759,299),'',None),
        ('EyeLeftOpen',src,(529,302,620,374),'eye_open',5),
        ('EyeRightOpen',src,(678,302,776,374),'eye_open',6),
        ('EyeLeftClosed',expression,(529,335,620,372),'eye_closed',5),
        ('EyeRightClosed',expression,(678,335,776,372),'eye_closed',6),
        ('MouthClosed',src,(620,407,680,441),'mouth_closed',7),
        ('MouthOpen',expression,(620,405,681,445),'mouth_open',7),
    ]
    for name, im, rect, kind, control in patches:
        cut = im.crop(rect).convert('RGBA')
        mask = Image.new('L',cut.size)
        ImageDraw.Draw(mask).rounded_rectangle((2,2,cut.width-3,cut.height-3),radius=5,fill=255)
        cut.putalpha(mask.filter(ImageFilter.GaussianBlur(1.1)))
        placement = (packed_x, 1280);atlas.paste(cut,placement);packed_x += cut.width+8
        mesh(name,rect,placement,9,[0,1,2,3]+([control] if control is not None else []),kind,control)
    atlas.save(OUT/'textures/atlas.png')
    canvas={'pixelsPerUnit':SIZE/2,'originX':SIZE/2,'originY':SIZE/2,'width':SIZE,'height':SIZE,'flags':0}
    (OUT/'model.moc3').write_bytes(write_moc3(build_moc3(canvas,params,parts,meshes)))
    model={'Version':3,'FileReferences':{'Moc':'model.moc3','Textures':['textures/atlas.png'],
           'Motions':{'Idle':[{'File':'model.idle.motion3.json'}]}},
           'Groups':[{'Target':'Parameter','Name':'EyeBlink','Ids':['ParamEyeLOpen','ParamEyeROpen']},
                     {'Target':'Parameter','Name':'LipSync','Ids':['ParamMouthOpenY']} ]}
    (OUT/'model.model3.json').write_text(json.dumps(model,indent=2))
    idle=json.loads((ROOT/'web/models/changzheng/model.idle.motion3.json').read_text())
    idle['Curves']=[c for c in idle['Curves'] if c['Id']!='ParamBodyAngleX']
    counts=[(len(c['Segments'])-2)//3 for c in idle['Curves']]
    idle['Meta'].update(CurveCount=len(counts),TotalSegmentCount=sum(counts),TotalPointCount=sum(n+1 for n in counts))
    (OUT/'model.idle.motion3.json').write_text(json.dumps(idle))
    (OUT/'rig-source.json').write_text(json.dumps({'canvas':SIZE,'neck_pivot':[646,510],
        'neck_blend_y':[440,585],'hair_tip_region_y':[460,1050],
        'yaw_projection':{'max_degrees':16,'face_depth':115,'key_values':params[0].keys},'parts':specs},indent=2))
    print(json.dumps({'drawables':len(meshes),'parameters':len(params),'texture':[2048,2048],
                      'moc3_bytes':(OUT/'model.moc3').stat().st_size}))


if __name__ == '__main__': main()
