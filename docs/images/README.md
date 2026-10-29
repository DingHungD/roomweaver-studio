# Documentation images

Owner: Roomweaver Studio public documentation. The original five screenshots are real browser captures of the current production frontend at 1440 CSS pixels wide, captured on 2026-10-29 in an isolated local workspace. They are not mockups or generated UI images.

Inputs for the original five captures: the repository's public `examples/from-dxf/project04-plan.dxf` and verified `examples/from-3d` native/GLB pair. All three project names are public demonstration labels. No private project registry, source drawings, credentials or machine paths were used in the captures.

- `studio-home-20261029.png`: public-only project library.
- `studio-import-20261029.png`: the three current import routes.
- `studio-plan-20261029.png`: DXF review after confirming the documented millimetre unit; Agent interpretation and design adoption remain pending.
- `studio-source-20261029.png`: source model render settings and a genuinely completed website run.
- `studio-website-20261029.png`: the generated panorama website, using the public example's existing camera and native lighting.

To recreate: build the frontend, start a separate empty workspace, create demonstration projects, open the bundled DXF and 3D examples, and capture the indicated pages. For source rendering, preserve/adopt the verified example scene with its supplied viewpoints before generating the site; automatic camera discovery alone did not find a safe point for this example. The first failed run was retained locally, then source rendering succeeded with the example viewpoints. No Agent/cloud call was made for these captures.

These images are intentional published documentation assets. Local capture scripts, job logs and source/model copies remain in ignored `artifacts/readme-ui-20261029/`; they may be rebuilt and are not required by the application. Keep published images while README references them. Older `studio-lighting.png` and `studio-plan-soft.png` belong to historical validation and are not screenshots of this release.

## Authorized 1020 reference editor demonstration

`studio-editor-reference-20261029.png` shows the real 02 editor at 1600 CSS pixels wide, using an isolated copy of the existing 1020.skp-derived prepared model and saved editing scene. The user explicitly authorized this screenshot demonstration. The isolated workspace uses an explicit reference-demo resume route to open the saved scene in 02; normal new GLB/SKP intake still opens the source-model website page. This is not evidence of a completed Project09 DWG interpretation, adoption or design review. The source model, scene snapshots, copy registration, provenance and capture scripts remain in ignored local artifacts/readme-editor-20261029/. Only the reviewed screenshot is published; no raw DWG/SKP, project registry, private source files or full case records are distributed.
