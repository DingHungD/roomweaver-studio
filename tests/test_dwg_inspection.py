"""Synthetic native-object checks; no client DWG or LibreDWG installation needed."""
import copy

import ezdxf
import pytest

from interior.workbench.studio.dwg_inspection import catalog, compare_dxf, handle


def document():
    return dict(created_by='synthetic', FILEHEADER=dict(version='AC1032'), HEADER=dict(INSUNITS=1),
        OBJECTS=[dict(object='LAYER', handle=[0, 1, 16], name='doors'),
                 dict(object='BLOCK_HEADER', handle=[0, 1, 31], name='*Model_Space',
                      entities=[[3, 2, 100, 100], [3, 2, 101, 101]]),
                 dict(entity='ARC', handle=[0, 1, 100], layer=[5, 1, 16, 16],
                      center=[10., 20., 0.], radius=80., start_angle=0., end_angle=1.5707963267948966),
                 dict(entity='TEXT', handle=[0, 1, 101], layer=[5, 1, 16, 16],
                      text_value='入口／80', ins_pt=[10., 20.], alignment_pt=[0., 0.], height=5.)])


def test_catalog_retains_annotation_coordinates_and_distinguishes_spaces():
    native = document()
    native['OBJECTS'].append(dict(entity='TEXT', handle=[0, 1, 102], text_value='block only'))
    before = copy.deepcopy(native)
    inventory, entities = catalog(native)
    assert len(entities) == 2
    assert inventory['annotations'][0]['text'] == '入口／80'
    assert inventory['annotations'][0]['insertion'] == [10., 20.]
    assert inventory['header_insunits'] == 1  # No automatic override to centimetres.
    assert native == before
    assert handle([12, 1, 5, 105]) == 105  # Resolved value, not relative offset.


def test_catalog_does_not_silently_drop_broken_references():
    native = document()
    native['OBJECTS'][1]['entities'].append([3, 1, 255, 255])
    with pytest.raises(ValueError, match='Unresolved'):
        catalog(native)


def test_independent_comparison_detects_door_shift_and_annotation_change(tmp_path):
    dxf = ezdxf.new('R2018')
    dxf.layers.new('doors')
    model = dxf.modelspace()
    arc = model.add_arc((10, 20), 80, 0, 90, dxfattribs=dict(layer='doors'))
    text = model.add_text('入口／80', dxfattribs=dict(layer='doors', insert=(10, 20), height=5))
    native = document()
    for o, e in zip(native['OBJECTS'][2:], [arc, text]):
        o['handle'][2] = int(e.dxf.handle, 16)
    native['OBJECTS'][1]['entities'] = [[3, 1, o['handle'][2], o['handle'][2]] for o in native['OBJECTS'][2:]]
    path = tmp_path/'derived.dxf'
    dxf.saveas(path)
    result = compare_dxf(native, path)
    assert result['differences'] == []
    assert result['missing_in_dxf'] == []
    arc.dxf.center = (10, 35, 0)
    text.dxf.text = '入口／90'
    dxf.saveas(path)
    result = compare_dxf(native, path)
    assert len(result['differences']) == 2


def test_unsupported_object_is_unverified_instead_of_passed(tmp_path):
    native = document()
    dxf = ezdxf.new()
    point = dxf.modelspace().add_point((1, 2))
    point.dxf.layer = 'doors'
    dxf.layers.new('doors')
    native['OBJECTS'] = native['OBJECTS'][:2] + [dict(entity='POINT',
        handle=[0, 1, int(point.dxf.handle, 16)], layer=[5, 1, 16, 16])]
    native['OBJECTS'][1]['entities'] = [[3, 1, int(point.dxf.handle, 16), int(point.dxf.handle, 16)]]
    path = tmp_path/'point.dxf'
    dxf.saveas(path)
    result = compare_dxf(native, path)
    assert len(result['unverified']) == 1
    assert result['verified_types'] == {}
