# Demo apartment

所有者：Roomweaver Studio。這是教學與測試用原創 6 × 4 公尺合成房間，沒有客戶圖面、外部家具或下載貼圖。程式與輸出採 repo 的 MIT 授權。

- **匯入入口：[demo-apartment.glb](demo-apartment.glb)**，含牆面、天花、地板、沙發、茶几、餐桌、兩張獨立椅子、檯面與兩個實際點光源。
- [layout.png](layout.png)：同模型隱藏天花後產生的上視參考圖，不是本版可匯入的 3D 輸入。
- [manifest.json](manifest.json)：尺寸、公尺座標、鏡位及 GLB／平面圖雜湊。
- [render-preview.png](render-preview.png)：獨立版實際 Cycles smoke test 的 Living 方向圖，640 × 480。
- [build_example.py](build_example.py)：幾何及材質生成來源；使用簡單幾何與純色材質，主要驗證操作流程。

此範例是最小 fixture；現行操作範例請用 [3D 教學公寓](../../../../examples/from-3d/README.md)。建立空案件後匯入本 GLB，新增 Living（2.5, 1.1, 1.6 m，135°）及 Dining（3.1, 2.2, 1.6 m，0°）觀看點，每點一個 24 mm 水平方向，確認後低解析出圖。匯入後修改存放使用者的 workspace，不修改此資料夾。

重建時，在 repo 根目錄設定 `INTERIOR_BLENDER`，執行：

```powershell
& $env:INTERIOR_BLENDER --background --disable-autoexec --python-exit-code 1 --python tests/fixtures/legacy-examples/demo-apartment/build_example.py
```

會重新產生 GLB、平面圖及 manifest，不同 Blender 版本可能有不同雜湊。示意效果圖可用 `tools/smoke_render.py` 重建，取該次 run 的 `view1-front.png`。這是固定教學輸入，不要把私人工作結果複製回這裡。
