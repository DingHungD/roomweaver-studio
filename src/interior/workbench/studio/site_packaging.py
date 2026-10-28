"""Portable presentation packaging; no runtime dependency on an external case."""
from pathlib import Path
import shutil
import zipfile
from PIL import Image,ImageOps
from ..storage import read_json,write_json


def copy_viewer(site):
    site=Path(site)
    dist=Path(__file__).resolve().parents[2]/'workbench_web/dist'
    manifest=read_json(dist/'.vite/manifest.json')
    files={'source-site.html'};visited=set()
    def include(item):
        if item['file'] in visited:return
        visited.add(item['file']);files.add(item['file']);files.update(item.get('css',[]));files.update(item.get('assets',[]))
        for dependency in item.get('imports',[]):include(manifest[dependency])
    include(manifest['source-site.html'])
    for name in files:
        target=site/('index.html' if name=='source-site.html' else name)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dist/name,target)
    html=site/'index.html';html.write_text(html.read_text(encoding='utf-8').replace('"/assets/','"./assets/'),encoding='utf-8')
    shutil.copyfile(html,site/'gallery.html')


def source_gallery(site):
    """Bridge raw-source renders to the enhanced gallery without inventing rooms."""
    site=Path(site);tour=read_json(site/'tour.json');scenes=[];nodes={}
    for view in tour['views']:
        camera='view-'+view['id'];thumbnail=f'renders/thumbs/{camera}.jpg'
        image=Image.open(site/view['still']);still_size=list(image.size)
        target=site/thumbnail;target.parent.mkdir(parents=True,exist_ok=True)
        ImageOps.fit(image,(320,200)).save(target,quality=85)
        with Image.open(site/view['panorama']) as panorama:panorama_size=list(panorama.size)
        x,y,z=view['eye']
        scenes.append(dict(id=camera,room=camera,label=view['name'],cameraId=camera,cameraLabel=view['name'],
            environment='day',mood='原模型照明',lightsState='on',lightGroupId='whole-model',still=view['still'],
            panorama=view['panorama'],stillSize=still_size,panoramaSize=panorama_size,thumbnail=thumbnail,
            position=[x,z,-y],yaw=180,pitch=-5))
        # Buttons mean camera jumps; no unverified door or floor markers.
        nodes[camera]=dict(label=view['name'],initialYaw=180,links=[])
    for scene in scenes:
        nodes[scene['cameraId']]['links']=[dict(to=s['cameraId'],label=s['label']) for s in scenes if s!=scene]
    write_json(site/'renders/gallery.json',dict(version=2,title=tour['title'],defaultScene=scenes[0]['id'],
        projection='equirectangular',renderer='Cycles / source-preserving',lightControls=False,
        rooms=[dict(id=s['room'],label=s['label'],defaultScene=s['id']) for s in scenes],scenes=scenes))
    write_json(site/'tour-navigation.json',dict(version=1,nodes=nodes))


def archive_site(output):
    output=Path(output);site=output/'site'
    with zipfile.ZipFile(output/'website.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(site.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(site).as_posix())
