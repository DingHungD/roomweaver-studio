"""Generate an entirely synthetic room for the optional AI layout workflow."""
from pathlib import Path
import ezdxf

doc = ezdxf.new()
doc.units = 6
model = doc.modelspace()
model.add_lwpolyline([(0, 0), (6, 0), (6, 6), (0, 6)], close=True, dxfattribs={'layer': 'floor'})
for a, b in [((0, 0), (6, 0)), ((6, 0), (6, 6)), ((6, 6), (0, 6)), ((0, 6), (0, 0))]:
    model.add_line(a, b, dxfattribs={'layer': 'wall'})
model.add_line((2.5, 0), (3.5, 0), dxfattribs={'layer': 'door'})
model.add_lwpolyline([(4, 4), (5.2, 4), (5.2, 4.5), (4, 4.5)], close=True, dxfattribs={'layer': 'furniture'})
doc.saveas(Path(__file__).with_name('study.dxf'))
