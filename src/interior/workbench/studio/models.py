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

class RenderFinish(Strict):
    """Non-destructive Cycles finish; original textures and UVs stay connected."""
    albedo_gain: tuple[float,float,float] = (1,1,1)
    roughness_delta: float = Field(default=0,ge=-.2,le=.25)
    bump_factor: float = Field(default=1,ge=.1,le=1)
    bevel: float = Field(default=0,ge=0,le=.003)
    textile: float = Field(default=0,ge=0,le=1)
    cabinet_front: Literal['none','+X','-X','+Y','-Y'] = 'none'

    @model_validator(mode='after')
    def bounded_color(self):
        if any(not .65<=v<=1.2 for v in self.albedo_gain):raise ValueError('材質色彩微調超出界限')
        return self

class Material(Strict):
    description: str = Field(default='', max_length=4000)
    url: str = Field(default='', max_length=2000)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    roughness: float = Field(default=.5, ge=0, le=1)
    render_roughness: float | None = Field(default=None, ge=.15, le=1)
    render_finish: RenderFinish | None = None
    candidate_id: str | None = None
    asset_reference: AssetReference | None = None

class ObjectAssignment(Strict):
    id: str
    name: str
    room_id: str | None = None
    material: Material = Field(default_factory=Material)

class AssetRequirements(Strict):
    purpose: str = Field(default='', max_length=60)
    dimension_source: Literal['unknown','confirmed','envelope','estimated'] = 'unknown'
    dimensions: tuple[float,float,float] | None = None
    evidence: str = Field(default='',max_length=1000)

    @model_validator(mode='after')
    def validate_source(self):
        from .asset_quality import PURPOSES
        if self.purpose and self.purpose not in PURPOSES:raise ValueError('未知用途分類')
        if self.dimensions and any(v<=0 or v>10000 for v in self.dimensions):raise ValueError('尺寸必須為正數公尺')
        if self.dimension_source in ('confirmed','envelope') and (not self.dimensions or not self.evidence.strip()):
            raise ValueError('已確認尺寸／範圍須填入三軸尺寸及來源')
        return self

class PlacementConstraints(Strict):
    area: tuple[float,float,float,float] | None = None
    max_distance: float = Field(default=0,ge=0,le=.5)
    keep_out: list[tuple[float,float,float,float]] = Field(default_factory=list,max_length=50)

    @model_validator(mode='after')
    def valid_rectangles(self):
        for r in ([self.area] if self.area else [])+self.keep_out:
            if r[0]>=r[2] or r[1]>=r[3] or any(abs(v)>10000 for v in r):raise ValueError('區域需為有效的世界座標矩形')
        if self.max_distance and not self.area:raise ValueError('自動移動必須指定允許區域')
        return self

class ObjectSpecification(Strict):
    purpose: str = Field(default='',max_length=60)
    front: Literal['unknown','+X','-X','+Y','-Y','multiple'] = 'unknown'
    front_source: Literal['suggested','user'] = 'suggested'
    material_policy: Literal['global','original','specified'] = 'global'
    material_description: str = Field(default='',max_length=2000)
    material_part: str = Field(default='',max_length=200)
    style: str = Field(default='',max_length=2000)
    dimension_fit: Literal['uniform','adapt'] = 'adapt'

    @model_validator(mode='after')
    def valid_purpose(self):
        from .asset_quality import PURPOSES
        if self.purpose and self.purpose not in PURPOSES:raise ValueError('未知用途分類')
        if self.material_policy=='specified' and not self.material_description.strip():raise ValueError('請填指定材質描述')
        return self

class GeneratedReference(Strict):
    task_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    model_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    purpose: str
    version: Literal[1,2] = 1
    source: Literal['bounded_parametric_template','agent_parametric'] = 'bounded_parametric_template'
    agent_task_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    quality: Literal['concept'] = 'concept'

    @model_validator(mode='after')
    def supported_generation(self):
        from .parametric_assets import SUPPORTED
        if self.purpose not in SUPPORTED:raise ValueError('不支援的概念家具用途')
        return self

class DecorContext(Strict):
    """Object identity survives replacement; support is a separate relationship."""
    purpose: Literal['vase','books','tableware','cookware','soap','plant','rug']
    support_group_id: str = Field(min_length=1,max_length=100)
    proposal_id: str = Field(pattern=r'^[a-f0-9]{32}$')

class FixtureInstallation(Strict):
    mode: Literal['surface','recessed','pendant']
    ceiling_group_id: str
    ceiling_z: float
    recess_depth: float = Field(ge=0,le=.08)
    agent_task_id: str | None = None
    verified: bool

class ObjectGroup(Strict):
    intake_metadata: dict = Field(default_factory=dict)
    fixture_installation: FixtureInstallation | None = None
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
    style_prompt: str | None = Field(default=None,max_length=2000)
    model_url: str = Field(default='',max_length=2000)
    asset_requirements: AssetRequirements | None = None
    object_specification: ObjectSpecification | None = None
    placement_constraints: PlacementConstraints | None = None
    asset_reference: AssetReference | None = None
    generated_reference: GeneratedReference | None = None
    decor_context: DecorContext | None = None

class Shot(Strict):
    aspect: Literal['4:3','16:9'] = '4:3'
    eye: tuple[float,float,float] | None = None
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name: str = Field(min_length=1, max_length=120)
    yaw: float = Field(ge=-360, le=360)
    pitch: float = Field(default=0, ge=-85, le=85)
    lens: float = Field(default=24, ge=12, le=150)
    shift_y: float = Field(default=0, ge=-.3, le=.3)

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


class ShelfRefinement(Strict):
    asset_bundle: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    object_id: str
    front: Literal['+X','-X','+Y','-Y']
    evidence: str = Field(min_length=8,max_length=2000)
    contents: list[Literal['microwave','coffee_machine','magazines']] = Field(default_factory=list,max_length=3)

class CompletionFront(Strict):
    group_id: str
    signature: str = Field(pattern=r'^[a-f0-9]{64}$')
    front: Literal['+X','-X','+Y','-Y']
    evidence: str = Field(min_length=8,max_length=2000)

class InstallationReplacement(Strict):
    group_id: str
    bundle: str = Field(pattern=r'^[a-f0-9]{32}$')

class DoorPartMaterial(Strict):
    color: str = Field(default="#bca07b",pattern=r"^#[0-9a-fA-F]{6}$")
    roughness: float = Field(default=.6,ge=0,le=1)

class DoorAssetBinding(Strict):
    bundle: str = Field(pattern=r"^[a-f0-9]{32}$")
    reference: AssetReference

class DoorControl(Strict):
    assets: dict[Literal["frame","leaf-0","leaf-1"],DoorAssetBinding] = Field(default_factory=dict)
    allow_width_adjustment: bool = False
    assembly_width: float | None = Field(default=None,ge=.5,le=3)
    min_passage: float = Field(default=.70,ge=.5,le=1.5)
    materials: dict[Literal["frame","leaf-0","leaf-1"],DoorPartMaterial] = Field(default_factory=dict)
    deleted: bool = False
    opening_id: str = Field(min_length=1,max_length=100)
    hinge: Literal['auto','A','B'] = 'auto'
    swing: Literal['auto','positive','negative'] = 'auto'
    name: str | None = Field(default=None,max_length=120)
    kind: Literal['single','double','sliding','frame','folding'] | None = None
    side: Literal['positive','negative'] | None = None

class ManualDoor(Strict):
    id: str = Field(pattern=r'^door-[a-f0-9-]{36}$')
    name: str = Field(min_length=1,max_length=120)
    points: tuple[tuple[float,float],tuple[float,float]]
    height: float = Field(default=2.1,gt=.3,lt=4)

    @model_validator(mode='after')
    def span(self):
        import math
        if not .25 < math.dist(*self.points) < 8:raise ValueError('門寬需介於 25 cm 與 8 m')
        return self

class Scene(Strict):
    intake_handoff: dict = Field(default_factory=dict)
    manual_doors: list[ManualDoor] = Field(default_factory=list,max_length=200)
    installation_replacements: list[InstallationReplacement] = Field(default_factory=list,max_length=100)
    door_controls: list[DoorControl] = Field(default_factory=list,max_length=200)
    completion_fronts: list[CompletionFront] = Field(default_factory=list,max_length=200)
    completion_details: bool = False
    opening_details: bool = False
    shelf_refinements: list[ShelfRefinement] = Field(default_factory=list,max_length=30)
    model_id: str
    rooms: list[Room] = Field(max_length=100)
    objects: list[ObjectAssignment] = Field(max_length=50000)
    groups: list[ObjectGroup] = Field(default_factory=list, max_length=50000)
    concept_furniture: list[ConceptFurniture] = Field(default_factory=list,max_length=200)
    design_notes: list[str] = Field(default_factory=list,max_length=1000)
    viewpoints: list[Viewpoint] = Field(default_factory=list, max_length=100)
    links: list[tuple[str, str]] = Field(default_factory=list, max_length=1000)
    lighting: Literal['existing'] = 'existing'
    ceiling_infill: list[str] = Field(default_factory=list,max_length=200)
    illustrative_exteriors: list[str] = Field(default_factory=list,max_length=30)
    lighting_setup: LightingSetup = Field(default_factory=LightingSetup)

    @model_validator(mode='after')
    def references(self):
        if len({r.group_id for r in self.installation_replacements})!=len(self.installation_replacements) or any(r.group_id not in {g.id for g in self.groups} for r in self.installation_replacements):raise ValueError('安裝替換需引用唯一現有家具')
        if len({d.opening_id for d in self.door_controls})!=len(self.door_controls):raise ValueError("門的設定不可重複")
        if len({d.id for d in self.manual_doors})!=len(self.manual_doors):raise ValueError('新增門不可重複')
        if len({f.group_id for f in self.completion_fronts})!=len(self.completion_fronts) or any(f.group_id not in {g.id for g in self.groups} for f in self.completion_fronts):raise ValueError('使用側證據必須引用存在且不重複的家具群組')
        if len(set(self.ceiling_infill))!=len(self.ceiling_infill) or any(k not in {o.id for o in self.objects} for k in self.ceiling_infill):raise ValueError("天花補面必須引用不重複的原生地板構件")
        if len(set(self.illustrative_exteriors))!=len(self.illustrative_exteriors) or any(k not in {g.id for g in self.groups} for k in self.illustrative_exteriors):raise ValueError('示意窗景必須引用存在且不重複的外窗群組')
        if len({f.id for f in self.concept_furniture})!=len(self.concept_furniture):raise ValueError('新增家具識別碼重複')
        for item in self.concept_furniture:
            group=next((g for g in self.groups if g.id==item.id),None)
            if group is None or set(group.children)!={p['id'] for p in item.parts}:raise ValueError('新增家具必須完整組成單物件')
        for items in (self.rooms, self.objects, self.viewpoints):
            if len({i.id for i in items}) != len(items):
                raise ValueError('識別碼不可重複')
        ids=[s.object_id for s in self.shelf_refinements]
        if len(ids)!=len(set(ids)) or any(k not in {o.id for o in self.objects} for k in ids):raise ValueError('層架細化需引用唯一現有物件')
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
    realism_all: bool = False
    prepare_openings: bool = False
    realism_brief: str = Field(default='',max_length=12000)
    base_revision: str
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    quality: Literal['preview', 'final'] = 'preview'
    scene_review: bool = False
    realism_point_id: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    agent_model: str | None = Field(default=None, max_length=120)

class ConfirmWorkflow(Strict):
    base_revision: str
    confirmation_id: str
