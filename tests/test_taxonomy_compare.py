"""A class migration must not quietly change masks, prune errors, or alter references."""
import numpy as np

from interior.object_recognition.taxonomy_compare import migrate_predictions,reference_for_training_ids


def test_migration_preserves_pixels_and_obsolete_false_positives():
    mask=np.ones((2,3),bool)
    original=[dict(class_id=15,class_name='water_heater',mask=mask,confidence=.7),
              dict(class_id=28,class_name='shelf',mask=mask,confidence=.5)]
    rows=migrate_predictions(original,[dict(id=0,name='wall'),dict(id=1,name='furniture')])
    assert rows[0]['class_id']==1 and rows[0]['class_name']=='furniture' and rows[0]['mask'] is mask
    assert rows[1]['class_id']==2 and rows[1]['class_name']=='unmapped_legacy_shelf'
    assert len(rows)==len(original) and original[0]['class_name']=='water_heater'
    assert rows[0]['confidence']==.7


def test_reference_uses_declared_training_id_without_mutating_canonical_id():
    old=dict(objects=[dict(id='a',class_id=29,training_class_id=1,class_name='furniture',exclusion_reason=None)])
    new=reference_for_training_ids(old,[dict(id=0,name='wall'),dict(id=1,name='furniture')])
    assert old['objects'][0]['class_id']==29 and new['objects'][0]['class_id']==1
    assert new['objects'][0]['canonical_class_id']==29
