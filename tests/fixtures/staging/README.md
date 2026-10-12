# Synthetic staging fixture

System test input owned by Roomweaver Studio. `create_scene.py` runs in Blender
with `-- <output-directory>` to build a new living/dining room. It contains no
Project03 data, case scripts or third-party assets. Generated BLEND/GLB and the
example registration manifest belong under `artifacts/staging-ui/`, are rebuildable,
and must not be committed. Public catalog downloads retain their own licenses.

From the repo root, with Blender on PATH:

```powershell
blender --background --python tests/fixtures/staging/create_scene.py -- artifacts/staging-ui/source
python -m interior.workbench example --directory artifacts/staging-ui/source --workspace artifacts/staging-ui/workspace --id STAGING_HOME
python -m interior.workbench serve --workspace artifacts/staging-ui/workspace --port 8876
```

In the UI choose the case, open its existing model, then use Lighting / Add decor.
These steps require an available Codex model for catalog matching and internet
access for BlenderKit. Original fixture generation does not download any assets.
Do not register over an existing case when repeating; choose a fresh workspace.
