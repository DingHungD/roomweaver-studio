"""Validated scene contract. Coordinates are Blender metres, Z up."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Room(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name: str = Field(min_length=1, max_length=120)

class AssetReference(Strict):
    asset_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    version_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    task_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    name: str = Field(max_length=200)
    url: str
    kind: Literal['model','material']
    license: str = Field(max_length=100)
    is_free: bool
    status: Literal['reference','applied'] = 'reference'

    @model_validator(mode='after')
    def source_url(self):
        if self.url!=f'https://www.blenderkit.com/asset-gallery-detail/{self.asset_id}/':raise ValueError('素材來源網址與 ID 不一致')
        return self

class Material(Strict):
    description: str = Field(default='', max_length=4000)
    url: str = Field(default='', max_length=2000)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    roughness: float = Field(default=.5, ge=0, le=1)
    candidate_id: str | None = None
    asset_reference: AssetReference | None = None

class ObjectAssignment(Strict):
    id: str
    name: str
    room_id: str | None = None
    material: Material = Field(default_factory=Material)

class ObjectGroup(Strict):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    children: list[str] = Field(min_length=1, max_length=50000)
    translation: tuple[float, float, float] = (0, 0, 0)
    rotation: float = Field(default=0, ge=-360, le=360)
    rotation_pivot: tuple[float, float, float] = (0, 0, 0)
    deleted: bool = False
    method: str = 'individual'
    editor_kind: Literal['furniture','decor'] | None = None
    design_prompt: str = Field(default='',max_length=2000)
    model_url: str = Field(default='',max_length=2000)
    asset_reference: AssetReference | None = None

class Shot(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name: str = Field(min_length=1, max_length=120)
    yaw: float = Field(ge=-360, le=360)
    pitch: float = Field(default=0, ge=-85, le=85)
    lens: float = Field(default=24, ge=12, le=150)

class Viewpoint(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    room_id: str
    name: str = Field(min_length=1, max_length=120)
    eye: tuple[float, float, float]
    shots: list[Shot] = Field(default_factory=list, max_length=12)

class StudioLight(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    name: str = Field(min_length=1,max_length=200)
    kind: Literal['AREA','POINT','SPOT','SUN'] = 'AREA'
    position: tuple[float,float,float]
    rotation: tuple[float,float,float] = (0,0,0)
    power: float = Field(default=150,ge=0,le=5000)
    color: tuple[float,float,float] = (1, .85, .65)
    size: float = Field(default=1,ge=.01,le=10)
    angle: float = Field(default=90,ge=1,le=179)
    shape: Literal['SQUARE','RECTANGLE','DISK','ELLIPSE'] = 'DISK'
    size_y: float = Field(default=1,ge=.01,le=10)
    sun_angle: float = Field(default=.00918,ge=0,le=3.14)
    spot_blend: float = Field(default=.5,ge=0,le=1)
    enabled: bool = True
    locked: bool = False
    group_id: str | None = None
    origin: Literal['native','restored','proposal','manual'] = 'manual'

    @model_validator(mode='after')
    def ranges(self):
        if any(abs(v)>10000 for v in self.position) or any(v<0 or v>1 for v in self.color):
            raise ValueError('光源位置或色彩超出範圍')
        if self.kind=='SUN' and self.power>10:raise ValueError('日光強度超出範圍')
        return self

class LightingSetup(Strict):
    enabled: bool = False
    mode: Literal['existing','day','indoor'] = 'existing'
    exposure: float = Field(default=0,ge=-3,le=3)
    auto_adjust: bool = True
    agent_review: bool = False
    source_job_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    lights: list[StudioLight] = Field(default_factory=list,max_length=200)

class ConceptFurniture(Strict):
    id: str = Field(pattern=r'^concept-[a-f0-9]{32}$')
    name: str = Field(min_length=1,max_length=100)
    asset: Literal['chair','desk','table','bed','sofa','cabinet','bunk_bed','washer','cooker','television','ceiling_light','floor_lamp','vase','books','cookware','tableware','soap','plant','rug']
    size: tuple[float,float,float]
    parts: list[dict] = Field(default_factory=list,max_length=30)

    @model_validator(mode='after')
    def geometry(self):
        from ...visualization.concept_geometry import parts
        expected=parts(self.id,self.asset,self.size)
        if self.parts and self.parts!=expected:raise ValueError('概念家具組成不符合類型及尺寸')
        self.parts=expected
        return self


class Scene(Strict):
    model_id: str
    rooms: list[Room] = Field(max_length=100)
    objects: list[ObjectAssignment] = Field(max_length=50000)
    groups: list[ObjectGroup] = Field(default_factory=list, max_length=50000)
    concept_furniture: list[ConceptFurniture] = Field(default_factory=list,max_length=200)
    design_notes: list[str] = Field(default_factory=list,max_length=1000)
    viewpoints: list[Viewpoint] = Field(default_factory=list, max_length=100)
    links: list[tuple[str, str]] = Field(default_factory=list, max_length=1000)
    lighting: Literal['existing'] = 'existing'
    lighting_setup: LightingSetup = Field(default_factory=LightingSetup)

    @model_validator(mode='after')
    def references(self):
        if len({f.id for f in self.concept_furniture})!=len(self.concept_furniture):raise ValueError('新增家具識別碼重複')
        for item in self.concept_furniture:
            group=next((g for g in self.groups if g.id==item.id),None)
            if group is None or set(group.children)!={p['id'] for p in item.parts}:raise ValueError('新增家具必須完整組成單物件')
        for items in (self.rooms, self.objects, self.viewpoints):
            if len({i.id for i in items}) != len(items):
                raise ValueError('識別碼不可重複')
        rooms = {r.id for r in self.rooms}
        lights=self.lighting_setup.lights
        if len({l.id for l in lights})!=len(lights):raise ValueError('光源識別碼不可重複')
        if any(l.group_id and l.group_id not in {g.id for g in self.groups} for l in lights):
            raise ValueError('光源綁定不存在的單物件')
        points = {p.id for p in self.viewpoints}
        if self.groups:
            members=[child for group in self.groups for child in group.children]
            if len({g.id for g in self.groups})!=len(self.groups) or len(members)!=len(set(members)) or set(members)!={o.id for o in self.objects}:
                raise ValueError('單物件必須完整且不重複地包含模型子物件')
            if any(abs(v)>10000 for g in self.groups for v in g.translation):
                raise ValueError('移動範圍超出限制')
        for obj in self.objects:
            if obj.room_id is not None and obj.room_id not in rooms:
                raise ValueError('物件引用不存在的空間')
        for point in self.viewpoints:
            if point.room_id not in rooms or len({s.id for s in point.shots}) != len(point.shots):
                raise ValueError('觀看點的空間或方向識別碼無效')
            if any(s.id=='panorama' for s in point.shots):
                raise ValueError('panorama 為全景保留識別碼')
        normalized = []
        for a, b in self.links:
            if a == b or a not in points or b not in points:
                raise ValueError('觀看點連結無效；刪點時請一起移除關聯')
            edge = tuple(sorted((a, b)))
            if edge not in normalized:
                normalized.append(edge)
        self.links = normalized
        return self

class SaveScene(Strict):
    base_revision: str | None
    scene: Scene

class StartWorkflow(Strict):
    base_revision: str
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    quality: Literal['preview', 'final'] = 'preview'

class ConfirmWorkflow(Strict):
    base_revision: str
    confirmation_id: str
