# 完整 3D 原模型出圖與網站

2026-10-28：已同步 上游製作流程 的完成版全屋 v5 展示方法：沉浸式導覽、實際開／關燈配對、4K 優先／原生 8K 延後載入、資源預算與回退。新增「同步最新 8K 交付」，核對同一 SKP、完成交付、母檔／圖檔／驗收雜湊後重用結果；不重複渲染或修形。詳見 [上游製作與同步邊界](SOURCE_WEBSITE_UPSTREAM.md)。

用途與所有者：跨案件共用功能。GLB／SKP 在 01 完成準備後直接進「原模型出圖／網站」，不採用編輯修訂、不進 02；PNG／JPG／DWG／DXF 仍走平面確認、配置與編輯。既有 3D 專案恢復時也走直接出圖。歷史編輯修訂保留。

出圖設定另外提供曝光差值 -3～+3 EV，不變更材質。CLI 的 `--exposure` 與 API 的 `exposure` 對應同一設定。獨立執行完成後寫入 `source-site.json` 收據，與佇列成果一起列於原模型頁；只讀取本案且來源／模型相符的完成紀錄。原模型指紋使用批次讀取網格陣列，避免大型模型逐頂點文字序列化。

來源：`workflows/interior-studio/source.json` 及來源雜湊相符的 `studio.prepare` 模型。舊匯入僅允許 current 模型的 source_sha256 與來源一致時回溯。嚴格保留渲染不接受任意模型路徑，不套用外案座標、材質修改或 pickle 快取；已完成製作版本則經獨立的同來源交付核對後重用，並標示其渲染副本有修形／材質細化。

正式入口：01 的完整 3D 匯入；API `GET/POST /api/studio/projects/{id}/source-site`。POST 包含 operation_id、model_id、quality（preview/final）、views（1–8）、lighting（native/preview/fixtures）。fixtures 只讀相同模型已啟用的照明；既有鏡位也只讀取 eye/name，其餘編輯欄位不傳入渲染器。native 不補光；preview 添加獨立環境光與鏡位補光，並非燈具配光設計。原本沒有燈光的 SKP 可選先前依燈具建立的照明。

獨立 Blender 程序直接開啟不可變 `model.blend`，不執行 studio_blender.py 的編輯／精修路徑。只在記憶體新增照明與攝影機，不儲存覆蓋 BLEND。出圖前後比較原物件世界矩陣、幾何、UV、材質指派及節點數值；檔案 SHA 再核對。這是 prepared 模型的保留驗證，不宣稱 SKP 與轉檔結果的逐像素一致。自動鏡位以地面及碰撞檢查取樣；既有眼點優先。未找到安全位置時明確失敗，不杜撰房間名稱。視角與轉檔材質仍需人工試圖確認。

產物：`runs/interior-studio/<job>/site/`、`website.zip`、`preservation.json`、`result.json`、Blender 日誌。來源與場景修訂不變。新執行可重建；舊成果不覆寫，正式交付應另存案件 deliverables。CLI 支援不經常駐伺服器執行：

```powershell
python -m interior.workbench source-site D:\path\project --model-id <prepared-id> --output-id <new-32-hex-id> --blender C:\path\blender.exe --views 3 --lighting fixtures
```

展示：`frontend/src/source-gallery` 保存已抽出的展示程式與原檔 SHA；`sourceSite.ts` 為入口，沒有外部案件執行依賴。包含沉浸式頁面、鏡位導覽、實際存在的開／關燈控制、4K／8K 讀取策略、需求重繪。ZIP 僅包含展示圖片、相對路徑清單及獨立 viewer，不含原 SKP、模型、工作室設定或登入資料。這是固定觀看點 360° 展示，不能任意行走。嚴格保留模式仍有 preview：1024 全景／800 效果圖、16 samples；final：4096／1920、96 samples。製作同步模式沿用已完成的原生 8192×4096、線性縮製 4096×2048、3200×2200 圖片，不將嚴格保留模式的試圖當成全屋 8K 製作。

每次新 Blender 出圖程序會探測可用 GPU，優先 OptiX，再選相容後端；沒有 GPU 時明示 CPU。`render-device.json` 分開記錄要求的裝置與原生 Cycles 日誌中的 Path tracing on／Denoising on；渲染失敗不自動換後端或隱瞞回退。既有製作同步完全不啟動 Blender。

本機可直接預覽或另開；ZIP 解壓後可部署至靜態網站主機。選定公開發布目標後另行部署，不自動覆蓋 上游製作流程 的既有公開站台。常駐後端需要重新載入新程式才會有新 API；前端建置 `node node_modules/vite/bin/vite.js build` 會同時產生工作室與獨立 viewer。

驗證：`tests/test_source_website.py` 驗證來源綁定、排隊去重、過期來源拒絕、場景不修改與網站檔案隔離；實際 Blender 合成測試及真模型試圖另外記錄於 artifacts／案件 run。
