# AI layout study (synthetic)

Owner: Roomweaver Studio example. `study.dxf` is a synthetic 6 × 6 m room with an entrance and an existing fixed cabinet. No client data or downloaded assets are included. `create_example.py` regenerates the DXF; keep the checked-in example for a reproducible import.

1. Create a test project and import `study.dxf` through the 2D DXF entrance.
2. On the plan confirmation page, open **AI 空間配置：家具與動線**.
3. Brief: `一人居住，需要安靜的居家工作區。保留既有櫃子與門窗，工作區要能從入口順暢到達。`
4. Required items (one per line): `新增一張工作桌` and `保留入口到工作桌及既有櫃子的通道`.
5. Keep the existing cabinet locked and passage target at 0.8 m. Connect the local Codex Agent, select an available model, and request a proposal.
6. Inspect the furniture, working zones, routes and assumptions. Adopt only after reviewing them, then confirm and build 3D.

Agent answers vary. Automatic checks reject collisions and insufficient route widths; a passed check is not a construction or regulatory approval. New furniture uses identifiable generic concept geometry, not purchasable products. Existing models and source files are preserved in prior revisions. Codex calls require ChatGPT login and consume the account's allowance; ordinary import/build does not require an Agent.
