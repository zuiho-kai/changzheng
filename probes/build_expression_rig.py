"""Frontal expression rig: local brows, eyelids, smile and mouth form, without yaw."""
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

WORK = ROOT / 'artifacts/runtime-expression-rig'
OUT = WORK / 'bundle'
SIZE = 1254


def smooth(a, b, x):
    t = max(0., min(1., (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def skin(x, y, values):
    """Continuous hand-painted equivalent weights: neck, head, shoulder and outer hair."""
    pitch, roll = (values.get(i, 0) / 30 for i in (1, 2))
    breath, hair = values.get(3, 0), values.get(4, 0)
    head = 1 - smooth(440, 585, y)
    outside = smooth(125, 225, abs(x - 646))
    head = max(head, outside * (1 - smooth(460, 1050, y)) * .65)
    angle = roll * math.radians(20)
    dx, dy = x - 646, y - 510
    rx = math.cos(angle) * dx - math.sin(angle) * dy - dx
    ry = math.sin(angle) * dx + math.cos(angle) * dy - dy
    # Frontal performance only. X is deliberately not bound to any mesh.
    nx = x + head * rx
    ny = y + head * (ry + 54 * pitch - dy * .025 * abs(pitch))
    # Breath translates the head with the shoulders; it never stretches facial features.
    # The upper body rises from the waist; face and neck move together.
    # This also gives a hop some shoulder movement instead of translating a card.
    ny -= 28 * breath * (1 - smooth(620, 1170, y))
    nx += (x - 646) * .0015 * breath * smooth(460, 700, y)
    nx += 12 * hair * outside * smooth(400, 900, y)
    # Coherent small body lean around the waist, shared by every face patch.
    body_angle = math.radians(values.get(15, 0) / 30 * 8)
    bx, by = nx - 646, ny - 1100
    nx, ny = 646 + math.cos(body_angle)*bx-math.sin(body_angle)*by, 1100+math.sin(body_angle)*bx+math.cos(body_angle)*by
    return ((nx / SIZE - .5) * 2, (ny / SIZE - .5) * 2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    src, blank, expression = [Image.open(ROOT / 'artifacts/changzheng-manual-assets' / f'{s}.png').convert('RGB') for s in ('source', 'blank', 'expression')]
    surprised = Image.open(ROOT / 'artifacts/changzheng-manual-assets/surprised.png').convert('RGB')
    assert surprised.size == (SIZE,SIZE)
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
    params += [EmitParam('ParamBreath', 0, 1, 0, [0, 1]), EmitParam('ParamHairSway', -1, 1, 0, [-1, 0, 1]),
               EmitParam('ParamEyeLOpen', 0, 1.25, 1, [0, .4, 1, 1.25]), EmitParam('ParamEyeROpen', 0, 1.25, 1, [0, .4, 1, 1.25]),
               EmitParam('ParamMouthOpenY', 0, 1, 0, [0, .25, 1])]
    params += [EmitParam('ParamMouthForm', -1, 1, 0, [-1, 0, 1]),
               EmitParam('ParamBrowLY', -1, 1, 0, [-1, 0, 1]), EmitParam('ParamBrowRY', -1, 1, 0, [-1, 0, 1]),
               EmitParam('ParamBrowLAngle', -1, 1, 0, [-1, 0, 1]), EmitParam('ParamBrowRAngle', -1, 1, 0, [-1, 0, 1]),
               EmitParam('ParamEyeLSmile', 0, 1, 0, [0, 1]), EmitParam('ParamEyeRSmile', 0, 1, 0, [0, 1]),
               EmitParam('ParamBodyAngleZ', -30, 30, 0, [-30, 0, 30])]
    params += [EmitParam('ParamSurprised', 0, 1, 0, [0, 1])]
    params += [EmitParam('ParamEyeBallX', -1, 1, 0, [-1, 0, 1]),
               EmitParam('ParamEyeBallY', -1, 1, 0, [-1, 0, 1])]
    params += [EmitParam('ParamRuntimeGaze', 0, 1, 1, [1])]
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
                if kind in ('eye_open','eye_surprise'): y = 355 + (y-355)*max(.06, v)
                smile = values.get(13 if 'Left' in name else 14, 0)
                if kind.startswith('eye_'): y -= smile * 8 * math.sin(math.pi * (x-x0)/(x1-x0))
                form = values.get(8, 0)
                if kind.startswith('mouth_'):
                    x = 650 + (x-650)*(1+.28*form)
                    y -= 5 * form * (abs(x-650)/40)**1.5
                if kind == 'mouth_open': y = 419 + (y-419)*(.08 + .92*v)
                if kind == 'brow':
                    left = name == 'BrowLeft'
                    y -= 7*values.get(9 if left else 10, 0)
                    y += 9*values.get(11 if left else 12, 0)*(x-(x0+x1)/2)/((x1-x0)/2)
                positions.append(skin(x,y,values))
            opacity = 1.
            if kind == 'eye_open': opacity = min(1, v/.4)*(1-values.get(16,0))
            elif kind == 'eye_surprise': opacity = min(1, v/.4)*values.get(16,0)
            elif kind == 'eye_closed': opacity = max(0, 1-v/.4)
            elif kind == 'mouth_open': opacity = min(1, v/.25)
            elif kind == 'mouth_closed': opacity = max(0, 1-v/.25)
            keys.append(positions);opacities.append(opacity)
        parts.append(EmitPart(name, 100+len(parts)*10))
        meshes.append(EmitMesh(name,len(parts)-1,0,uv,triangles,affect,keys,opacities))
        specs.append({'id':name,'rect':rect,'vertices':len(points),'controls':[params[i].id for i in affect]})

    mesh('BodyHeadSkin', (0,0,SIZE,SIZE), (0,0), 28, [1,2,3,4,15])
    # Viewer-left/right feature coordinates picked directly from the full-resolution drawing.
    patches = [
        ('BrowLeft',src,(548,268,618,296),'brow',None), ('BrowRight',src,(678,268,759,299),'brow',None),
        ('EyeLeftOpen',src,(529,302,620,374),'eye_open',5),
        ('EyeRightOpen',src,(678,302,776,374),'eye_open',6),
        ('EyeLeftSurprised',surprised,(529,302,620,374),'eye_surprise',5),
        ('EyeRightSurprised',surprised,(678,302,776,374),'eye_surprise',6),
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
        local = ([control] if control is not None else [])
        if kind.startswith('mouth_'): local += [8]
        if kind.startswith('eye_'): local += [13 if 'Left' in name else 14]
        if kind in ('eye_open','eye_surprise'): local += [16]
        if kind == 'brow': local += [9,11] if name == 'BrowLeft' else [10,12]
        mesh(name,rect,placement,9,[1,2,3,15]+local,kind,control)
    atlas.save(OUT/'textures/atlas.png')
    canvas={'pixelsPerUnit':SIZE/2,'originX':SIZE/2,'originY':SIZE/2,'width':SIZE,'height':SIZE,'flags':0}
    (OUT/'model.moc3').write_bytes(write_moc3(build_moc3(canvas,params,parts,meshes)))
    model={'Version':3,'FileReferences':{'Moc':'model.moc3','Textures':['textures/atlas.png'],
           'Motions':{'Idle':[{'File':'model.idle.motion3.json'}]}},
           'Groups':[{'Target':'Parameter','Name':'EyeBlink','Ids':['ParamEyeLOpen','ParamEyeROpen']},
                     {'Target':'Parameter','Name':'LipSync','Ids':['ParamMouthOpenY']} ]}
    idle=json.loads((ROOT/'web/models/changzheng/model.idle.motion3.json').read_text())
    idle['Curves']=[c for c in idle['Curves'] if c['Id'] not in ('ParamBodyAngleX','ParamAngleX','ParamAngleY')]
    counts=[(len(c['Segments'])-2)//3 for c in idle['Curves']]
    idle['Meta'].update(CurveCount=len(counts),TotalSegmentCount=sum(counts),TotalPointCount=sum(n+1 for n in counts))
    (OUT/'model.idle.motion3.json').write_text(json.dumps(idle))
    expressions = {
        'happy': {'ParamMouthForm':.9,'ParamEyeLSmile':1,'ParamEyeRSmile':1,'ParamEyeLOpen':0,'ParamEyeROpen':0,'ParamBrowLY':.35,'ParamBrowRY':.35},
        'curious': {'ParamMouthForm':-.25,'ParamBrowLY':.7,'ParamBrowRY':-.1,'ParamAngleZ':10},
        'surprised': {'ParamSurprised':1,'ParamEyeLOpen':1.12,'ParamEyeROpen':1.12,'ParamBrowLY':.9,'ParamBrowRY':.9,'ParamMouthForm':-.8},
        'serious': {'ParamEyeLOpen':.72,'ParamEyeROpen':.72,'ParamBrowLY':-.25,'ParamBrowRY':-.25,'ParamBrowLAngle':.55,'ParamBrowRAngle':-.55,'ParamMouthForm':-.6},
    }
    (OUT/'expressions').mkdir(exist_ok=True)
    model['FileReferences']['Expressions']=[]
    for name, values in expressions.items():
        path=f'expressions/{name}.exp3.json'
        (OUT/path).write_text(json.dumps({'Type':'Live2D Expression','FadeInTime':.3,'FadeOutTime':.4,'Parameters':[{'Id':k,'Value':v,'Blend':'Overwrite'} for k,v in values.items()]},indent=2))
        model['FileReferences']['Expressions'].append({'Name':name,'File':path})
    (OUT/'model.model3.json').write_text(json.dumps(model,indent=2))
    (OUT/'rig-source.json').write_text(json.dumps({'canvas':SIZE,'neck_pivot':[646,510],
        'neck_blend_y':[440,585],'hair_tip_region_y':[460,1050],
        'yaw_enabled':False,'gaze_driver':'avatar-performance.js runtime iris deformation',
        'performance':'frontal expressions, independent gaze and upper body rise','parts':specs},indent=2))
    print(json.dumps({'drawables':len(meshes),'parameters':len(params),'texture':[2048,2048],
                      'moc3_bytes':(OUT/'model.moc3').stat().st_size}))


if __name__ == '__main__': main()
