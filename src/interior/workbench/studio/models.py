"""Validated scene contract. Coordinates are Blender metres, Z up."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Room(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name: str = Field(min_length=1, max_length=120)

class Material(Strict):
    description: str = Field(default='', max_length=4000)
    url: str = Field(default='', max_length=2000)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    roughness: float = Field(default=.5, ge=0, le=1)
    candidate_id: str | None = None

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
    deleted: bool = False
    method: str = 'individual'

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

class Scene(Strict):
    model_id: str
    rooms: list[Room] = Field(max_length=100)
    objects: list[ObjectAssignment] = Field(max_length=50000)
    groups: list[ObjectGroup] = Field(default_factory=list, max_length=50000)
    viewpoints: list[Viewpoint] = Field(default_factory=list, max_length=100)
    links: list[tuple[str, str]] = Field(default_factory=list, max_length=1000)
    lighting: Literal['existing'] = 'existing'
    lighting_setup: LightingSetup = Field(default_factory=LightingSetup)

    @model_validator(mode='after')
    def references(self):
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
