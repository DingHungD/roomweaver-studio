"""Source-only CAD graphics, independent of editable modelling decompositions."""
import hashlib
import math
from pathlib import Path
import threading
import xml.etree.ElementTree as ET

import ezdxf
from ezdxf.addons.drawing import Frontend,RenderContext,svg,layout,config
from ezdxf.math import BoundingBox2d
from ezdxf.path import make_path,from_hatch_boundary_path

from .service import digest
from ..storage import read_json,write_json

VERSION='cad-source-v3'
_lock=threading.RLock()


def visible_in_modelspace(doc,entity):
    if entity.dxf.is_supported('invisible') and entity.dxf.get('invisible',0):return False
    # Some DXF writers omit a layer table entry; match the drawing frontend's
    # default visible-layer fallback rather than treating this as a hidden object.
    if entity.dxf.layer not in doc.layers:return True
    layer=doc.layers.get(entity.dxf.layer)
    return not layer.is_off() and not layer.is_frozen()


def source_geometry(path,factor,origin):
    """Keep separate source paths; never use tessellated floor or curve triangles."""
    doc=ezdxf.readfile(path);result=[]
    def emit(e,points,closed,suffix=''):
        pts=[[float(p[0])*factor-origin[0],float(p[1])*factor-origin[1]] for p in points]
        if len(pts)>1 and math.dist(pts[0],pts[-1])<1e-9:pts.pop();closed=True
        if len(pts)<2:return
        result.append(dict(id='e-'+e.dxf.handle+suffix,name=e.dxf.layer+' '+e.dxftype(),source_role='unclassified',layer=e.dxf.layer,kind=e.dxftype(),closed=closed,points=pts,source_handle=e.dxf.handle))
    for e in doc.modelspace():
        if not visible_in_modelspace(doc,e):continue
        kind=e.dxftype()
        if kind in ('TEXT','MTEXT','ATTDEF','ATTRIB','DIMENSION'):continue
        if kind=='LINE':emit(e,[e.dxf.start,e.dxf.end],False);continue
        if kind=='LWPOLYLINE' and not any(p[4] for p in e.get_points()):
            emit(e,list(e.vertices_in_wcs()),e.closed);continue
        try:
            if kind=='HATCH':
                for index,boundary in enumerate(e.paths):
                    p=from_hatch_boundary_path(boundary,e.ocs(),elevation=e.dxf.elevation.z)
                    for j,part in enumerate(p.sub_paths()):
                        emit(e,list(part.flattening(.001/factor)),part.is_closed,f'-boundary-{index}'+(f'-sub-{j}' if j else ''))
            elif kind in ('POLYLINE','LWPOLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE'):
                for j,part in enumerate(make_path(e).sub_paths()):
                    emit(e,list(part.flattening(.001/factor)),part.is_closed,f'-sub-{j}' if j else '')
        except (ValueError,TypeError,AttributeError,NotImplementedError):
            # Unsupported interpretation remains in intake issues. The independent
            # CAD drawing frontend below can still display supported glyphs.
            continue
    return result


class SourceSvgBackend(svg.SVGRenderBackend):
    """Keep draw order, original layers and handles on every generated graphic."""
    def add_strokes(self,d,properties):
        n=len(self.entities);super().add_strokes(d,properties)
        if len(self.entities)>n:self.tag(self.entities[-1],properties)
    def add_filling(self,d,properties):
        n=len(self.entities);super().add_filling(d,properties)
        if len(self.entities)>n:self.tag(self.entities[-1],properties)
    @staticmethod
    def tag(element,properties):
        element.set('data-cad-layer',properties.layer)
        element.set('data-cad-handle',properties.handle)


class SourceSvgRecorder(svg.SVGBackend):
    @staticmethod
    def make_backend(page,settings):return SourceSvgBackend(page,settings)


class SourceContext(RenderContext):
    """Use an installed CJK face when a missing CAD bigfont would draw boxes."""
    def __init__(self,doc):
        super().__init__(doc);self.substitutions=set();self.missing_glyphs=False
    def resolve_font(self,entity):
        from ezdxf.fonts import fonts
        if not entity.dxf.is_supported('style'):return None
        face=super().resolve_font(entity)
        text=entity.plain_text() if hasattr(entity,'plain_text') else ''
        if not text and entity.dxf.is_supported('tag'):text=entity.dxf.get('tag','')
        chars={ord(c) for c in text if 0x3400<=ord(c)<=0x9fff or 0xf900<=ord(c)<=0xfaff}
        if not chars:return face
        manager=fonts.font_manager
        def supports(name):
            try:return manager.has_font(name) and chars.issubset(manager.get_ttf_font(name).getBestCmap())
            except (ValueError,OSError,KeyError,AttributeError):return False
        if face and supports(face.filename):return face
        for name in ('msjh.ttc','simsun.ttc','kaiu.ttf','NotoSansCJK-Regular.ttc','NotoSansTC-Regular.ttf','NotoSansSC-Regular.ttf'):
            if supports(name):
                self.substitutions.add((face.filename if face else 'default',name))
                return manager.get_font_face(name)
        self.missing_glyphs=True
        return face


def record(path):
    doc=ezdxf.readfile(path);backend=SourceSvgRecorder();context=SourceContext(doc)
    configuration=config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
        image_policy=config.ImagePolicy.IGNORE,lineweight_policy=config.LineweightPolicy.RELATIVE,
        hatching_timeout=15)
    Frontend(context,backend,config=configuration).draw_layout(doc.modelspace(),finalize=True)
    backend.font_substitutions=sorted(context.substitutions)
    backend.missing_glyphs=context.missing_glyphs
    return doc,backend


def frame(doc,backend):
    """Fit the annotated drawing by default, keeping distant drafting marks in the file."""
    from ezdxf import bbox
    annotations=[e for e in doc.modelspace().query('TEXT MTEXT DIMENSION') if visible_in_modelspace(doc,e)]
    bounds=bbox.extents(annotations)
    whole=backend.player().bbox()
    if not bounds.has_data or max(bounds.size.x,bounds.size.y)<1:bounds=whole
    # Nearby source strokes may extend past labels. Do not include isolated far
    # reference marks when fitting the main plan; the SVG retains their paths.
    pad=max(bounds.size.x,bounds.size.y)*.025 or 1
    region=BoundingBox2d([(bounds.extmin.x-pad,bounds.extmin.y-pad),(bounds.extmax.x+pad,bounds.extmax.y+pad)])
    return region,whole


def generate(path,raw_bounds=None):
    """Render actual entities, hatching, dimensions, bulges and polyline widths."""
    doc,backend=record(path)
    region,whole=frame(doc,backend)
    if raw_bounds:region=BoundingBox2d([(raw_bounds[0],raw_bounds[1]),(raw_bounds[2],raw_bounds[3])])
    width=420.;height=width*region.size.y/region.size.x
    root=backend.get_xml_root_element(layout.Page(width,height),settings=layout.Settings(output_coordinate_space=1000000,max_stroke_width=.0015,min_stroke_width=.12),render_box=region)
    matrix=list(backend.transformation_matrix)
    width,height=map(float,root.attrib['viewBox'].split()[2:])
    # Prefix CSS classes: inline SVG styles must not affect unrelated app icons.
    prefix='cad_'+hashlib.sha256((str(path)+str(raw_bounds)).encode()).hexdigest()[:12]+'_'
    for element in root.iter():
        if element.tag=='style' and element.text:element.text=element.text.replace('.C','.'+prefix+'C')
        if 'class' in element.attrib:element.set('class',' '.join(prefix+c for c in element.get('class').split()))
    markup=''.join(ET.tostring(e,encoding='unicode') for e in root)
    # Only this renderer generates markup. Source text becomes glyph paths, not HTML.
    if any(e.tag in ('script','foreignObject','image') for e in root.iter()):raise ValueError('CAD 預覽含未支援的外部內容')
    layer_names=sorted({e.get('data-cad-layer') for e in root.iter() if e.get('data-cad-layer') is not None})
    rb=[region.extmin.x,region.extmin.y,region.extmax.x,region.extmax.y]
    return dict(version=VERSION,markup=markup,width=width,height=height,viewBox=f'0 0 {width:g} {height:g}',
        matrix=[matrix[0],matrix[1],matrix[4],matrix[5],matrix[12],matrix[13]],
        raw_bounds=rb,full_bounds=[whole.extmin.x,whole.extmin.y,whole.extmax.x,whole.extmax.y],
        view=dict(width=width,height=height,bounds=rb,scale=width/region.size.x,pad=0),
        layers=layer_names,source_entities=len(doc.modelspace()),drawing_paths=sum(e.tag=='path' for e in root.iter()),
        font_substitutions=backend.font_substitutions,missing_glyphs=backend.missing_glyphs,
        limitations=['外部貼圖／未載入參考不在此向量預覽中','缺少 CAD 中文 bigfont 時使用已安裝且含對應字形的中文字型；字體不代表CAD原字型完全等價']+(['缺少中文字形，請安裝對應 CJK 字型後重建預覽'] if backend.missing_glyphs else []))


def drawing_packet(studio,plans,project,plan):
    packet=plans.current(project,plan);root=studio.root(project);source=packet['source']
    if packet['parsed'].get('image'):raise ValueError('圖片不需 CAD 向量預覽')
    for item in [source]+([source['original']] if source.get('original') else []):
        if digest(root/item['path'])!=item['sha256']:raise ValueError('CAD 原件或轉檔已變動，無法顯示原圖')
    key=hashlib.sha256((VERSION+source['sha256']).encode()).hexdigest()
    folder=root/'runs/cad-source-preview'/key;cache=folder/'source.json'
    with _lock:
        if cache.exists():return read_json(cache)
        result=generate(root/source['path']);result.update(source_sha256=source['sha256'],original_sha256=(source.get('original') or source)['sha256'])
        if digest(root/source['path'])!=source['sha256']:raise ValueError('CAD 在顯示準備期間變動')
        write_json(cache,result)
        (folder.parent/'README.md').write_text('# CAD來源顯示快取\n\n所有者：本案。僅由原始DXF／DWG核對後的DXF產生，不能使用建模分片或SEMANTIC候選作原圖。source.json保存渲染版本、來源雜湊、SVG與座標矩陣；不代表已確認設計。可從原件重建，沒有設計修訂引用這些顯示快取時可清理。\n',encoding='utf8')
        return result


def raw_frame(view,factor,origin):
    left=(view['bounds'][0]-view['pad']/view['scale']+origin[0])/factor
    top=(view['bounds'][3]+view['pad']/view['scale']+origin[1])/factor
    return [left,top-view['height']/view['scale']/factor,left+view['width']/view['scale']/factor,top]


def rasterize(markup,path,width,height):
    """Agent screenshots use the same source renderer as the visible SVG."""
    try:from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError('CAD 原圖看圖預覽需要 agent 選用依賴：pip install -e ".[agent]"；再執行 python -m playwright install chromium。') from exc
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport=dict(width=width,height=height),device_scale_factor=1)
                page.route('**/*',lambda route:route.abort())
                page.set_content(f'<html><head><style>html,body{{margin:0;overflow:hidden}}svg{{width:100vw;height:100vh;display:block}}</style></head><body>{markup}</body></html>')
                page.screenshot(path=str(path))
            finally:browser.close()
    except Exception as exc:
        if 'Executable doesn' in str(exc):
            raise ValueError('CAD 原圖看圖預覽需要本機 Chromium：請執行 python -m playwright install chromium。未使用建模分片代替原圖。') from exc
        raise ValueError('CAD 原圖預覽擷取失敗：'+str(exc)[:400]) from exc


def draw_source_image(path,view,factor,origin,target):
    result=generate(path,raw_frame(view,factor,origin))
    outer=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{result["viewBox"]}">{result["markup"]}</svg>'
    target.with_suffix('.svg').write_text(outer,encoding='utf8')
    rasterize(outer,target,view['width'],view['height'])
