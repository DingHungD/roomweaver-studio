# SketchUp 本機匯入與轉檔

所有者：Roomweaver 共用 3D 輸入功能。核心為 `src/interior/visualization/sketchup.py`，背景程序入口為 `studio/skp_conversion.py`。私人 SKP 不作公共測試或範例，不傳送到雲端轉檔服務。

## 安裝與操作

在 Roomweaver repo 根目錄使用相同 Python 環境安裝免費的 [OpenSKP](https://github.com/iamahsanmehmood/openskp) 1.3.0，再建置前端、重新啟動服務：

```powershell
.\.venv\Scripts\python.exe -m pip install -c requirements-lock.txt -e ".[sketchup]"
npm run build --prefix frontend
```

在「01 匯入 → 開啟 3D 模型」直接選 `.skp` 或 `.glb`，兩者上限皆為 512 MB。SKP 轉檔是背景模型工作的一部分，最長 30 分鐘；大型檔案需較多 RAM。無需 SketchUp、付費匯入器、Agent 訂閱或 API key。缺少選用依賴時工作會顯示安裝命令並保留原件，不能只修改檔案副檔名。

單獨轉檔也可使用 CLI。`--output` 必須為尚不存在的新目錄，避免覆寫舊成果；省略 `--blend` 時只產 GLB，不需 Blender。

```powershell
.\.venv\Scripts\python.exe -m interior.workbench convert-model "C:\models\house.skp" --output "C:\models\converted-v1" --blend --workspace workspace
```

Blender 位置沿用 `--blender`、`INTERIOR_BLENDER` 或指定 workspace 的 runtime 設定。輸出為 `model.glb`、選用 `model.blend`、`conversion.json`、選用 `blender-readback.json` 及日誌。檔案可直接用 Blender 開啟；GLB 可供其他 3D 工具使用。

## 工作流與資料契約

`SKP 原件 → OpenSKP 解析／可見性過濾 → 公尺、Y-up、嵌入貼圖、共用網格的 GLB → Blender 回讀 → Roomweaver 原有物件 ID／尺度交接檢查 → 採用後編輯`。

- 使用本案 `sources/workbench/<batch>/` 保存不可變原件；設定及來源快照在 `workflows/interior-studio/`。
- UI 的轉檔結果與證據放在 `runs/interior-studio/<job>/sketchup/`，工作模型仍為同一 job 的 `model.blend`／`model.glb`；來源 SHA、工具版本、輸出 SHA、物件／材質／貼圖數與排除項目保存在 `conversion.json`。
- 原件在轉換前後均核對 SHA。失敗不更新現行編輯修訂；以新的操作識別重試，原失敗紀錄保留。同一識別碼不能換檔案或重建效果。
- OpenSKP 的 Python 預設 GLB 匯出會把座標轉為毫米；Roomweaver 直接序列化其公尺制 instanced scene，避免 1,000 倍尺度錯誤。節點保留來源名稱／定義／圖層／GUID，網格與貼圖共享，不做自動減面。
- 有剪切的仿射元件矩陣以 SVD 分解成兩層可分解為 TRS 的節點，精確保持原矩陣乘積及頂點。Blender 匯入單一剪切矩陣會因 TRS 分解造成偏移，不能以放寬 2 cm／2% 交接容差通過；此處不修改共同檢查門檻。
- Studio 沿用 SKP 原有頂層元件實例為選取分組；未分組表面獨立保存，不把零件數當成家具數。瀏覽器重新分組時保留精確仿射矩陣，避免 Three.js 的 TRS 重新分解變形；保留每個子網格供材質細調。這不等於自動識別家具用途。
- 為遵守來源隱藏旗標，1.3.0 的解析工作副本經薄 adapter 過濾後再建場景；不使用會再次解析並丟失過濾結果的便利方法。這是有版本約束的相容處理，升級 OpenSKP 須重跑 SKP 與 Blender 合成測試。

本目錄內資料皆可由原件和相同工具重建；仍有修訂引用的成果不能當暫存清理。CLI 輸出不自行登記或覆寫既有 Roomweaver 專案。

## 保留與限制

保留可見表面網格、元件實例、巢狀變換、基本材質／透明度及 PNG／JPEG 貼圖與 UV。原件內明確隱藏的物件、面與圖層不作可見網格輸出；來源原件仍完整保留。

SketchUp 尺寸文字、施工線、剖切顯示、場景鏡位、樣式及 Enscape／V-Ray 等外掛材質／燈光不會自動成為 Blender 等價設定。GLB 是網格，不自動帶來牆門窗或空間的業務語意。較舊 SKP 的名稱編碼及特殊模型仍需比對來源；解析失敗會明確停止。不能將轉檔、同檔回讀或介面可操作視為完整設計／視覺保真驗收。

匯入後可在「光源」頁按 [依現有燈具建立光源](FIXTURE_LIGHTING.md)，讓所選 Agent 辨識保留下來的燈具模型，依原生局部圖與量測表面建立可調整光源。這是可選的推定配置，不是外掛燈光還原；轉檔本身仍可完全離線，也不會自動送出模型資料。

測試入口：`tests/test_sketchup_import.py`、`tests/integration/test_sketchup_pipeline.py`。使用不同尺度／原點／旋轉及剪切的合成檔，驗證來源不變、實例共用、貼圖、隱藏、錯檔、來源變動、重播與匯入隔離；實際 Blender 測試另外執行，不用 mock 結果宣稱已實測。
