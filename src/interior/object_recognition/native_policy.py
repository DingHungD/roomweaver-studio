"""Reusable CAD interpretation policy; no case IDs, answer masks or coordinates."""
import copy
from shapely.geometry import Polygon

VERSION='native-whole-object-v2'
GUIDANCE='''原生整件判讀技巧（跨案通用，不是本圖答案）：
1 類別先看圖樣與周邊構件，再以原生文字、引線、方向佐證；最近文字或黑色本身不能定類。主要靠文字區分的方框家具／設備使用furniture，有明確圖形的床桌椅沙發保留細類。純文字需求或空白預留區不冒充已存在實體。
2 本案人類確認優先，不能用模型或跨案技巧推翻本案已確認類別、移除決定及備註。不確定就defer保留候選，不能以刪除不確定項提高精確率。
3 有外框的水槽／設備取整件外框，不能只框盆內緣或內部細線。櫃體取白色櫃體外框，避開同一大矩形內的鄰接黑牆；找真正四邊，不取最大片框。
4 相同物件可能分散在多段封閉幾何：窗框的中段玻璃、連續檯面的內嵌洗碗機區沒有獨立封閉polygon，仍屬整件占位。確認同一物件且共用外緣後用bounds或edge_bounds包完整範圍，不能用outline聯集留下人為空洞。窗各自分開，窗處不推測補上／下牆。
5 相連實心黑牆為一件；彼此不連通的黑牆分開。不能用大包框填白色櫃體／窗／洞口。已歸某牆的原生短牆段不能再歸另一牆；桌邊L形牆與外側主牆需查真實連通性。牆的凹形和孔洞保留，不使用凸包。
6 樑不能因黑色而改成牆。門洞以兩端門框相對的實際邊線界定，可用edge_bounds或pair，不直接拿包含門框／牆端的大包框代替淨洞。
7 closed旗標未設不代表圖樣開放：若首末點完全相等且形成有效正面積多邊形，衍生來源可視為閉合，原始座標不變；有縫則不得自行接線。
8 椅背等曲線家具取整件占位，填內部空白但不納入矩形外角的多餘空白。若適用，可用hull方法從同件物件原生線／弧的所有點形成凸包；不得混入桌線或用於牆、樑、窗、門洞。所有頂點由來源推導，不自由填座標。
9 淋浴玻璃的固定隔屏與開啟門扇按封閉實體投影聯集；原生共享鉸接點可佐證同一組件。開門弧及構件之間空白不是玻璃。真正重複片段要指向存活的完整代表，不把互補兩片直接丟棄。
10 每一件都核對類別與完整邊界，高confidence不能跳過。邊界需改善則replace引用原生來源；keep只保留當前已複核版本。完成後看實際合併圖層、全圖及六區，再查漏／重複／完整外框。掃描必須列具體未解問題，已修正且通過的觀察放summary，不當成新問題反覆提出。沒有參考標註時不輸出precision／recall。
新增方法 {method:"hull",refs:[{id:"真實原生圖元"},...]} 僅供家具／椅／沙發整件占位，宿主由原生點計算凸包，不接受自由座標。
'''


def explicitly_closed(geometry):
    points=geometry.get('points',[])
    if len(points)<4 or points[0]!=points[-1]:return False
    shape=Polygon(points)
    return shape.is_valid and shape.area>0


def normalized_site(site):
    """Normalize only exact endpoint closure in an independent derived copy."""
    result=copy.deepcopy(site);audit=[]
    for geometry in result.get('geometry',[]):
        if not geometry.get('closed',False) and explicitly_closed(geometry):
            geometry['closed']=True
            audit.append(dict(id=geometry['id'],original_closed=False,derived_closed=True,
                endpoint_exact_equality=True,coordinates_changed=False))
    return result,audit
