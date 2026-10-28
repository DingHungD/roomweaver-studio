# 已完成製作交付同步（2026-10-28）

所有者：跨案件共用來源網站功能。輸入為使用者指定的製作根目錄、原始 SKP、靜態發布目錄及完成交付目錄。正式入口為 01 完整 3D 的「原模型出圖／網站」；先用共用 CLI 綁定已有製作，之後頁面的「同步最新 8K 交付」可沿用相同設定。

```powershell
python -m interior.workbench sync-source-site <project> --producer <producer-root> --source <source.skp> --site <published-dist> --deliveries <deliveries-root> --model-id <prepared-id> --output-id <new-32-hex-id> --prompt <workflow.txt>
```

設定存於案件 `workflows/source-website/upstream.json`。網站生成的 API 原契約增加 `mode=sync-production`，仍使用有去重／來源綁定的 `studio.source-site` 工作；沒有呼叫 Blender 或 Agent。未綁定製作來源的案件，仍可用原有嚴格保留出圖。此功能不會把某案的相機／材質／房間數拿來套用另一個 SKP。

## 最新方法如何接入

| 上游製作流程 全屋 v5 方法 | 整合行為 |
|---|---|
| 不重複製作已完成基線 | 依當前 gallery.json 的 SHA 找到 passed 的 delivery.json，核對發布 release hash、全部發布檔案、製作母檔、主要圖片壓縮包及各驗收報告 SHA，再重用 |
| 14 場景／42 主要成品／6 拍攝點 | 數量由實際清單與交付計算，非共用程式固定值；逐張核對 JPEG 實際尺寸、宣告尺寸、同鏡位開關配對與相同曝光／燈組 |
| 原生 8K、線性 4K、3200×2200 效果圖 | 保留上游已驗收的圖片位元組與製作摘要。EXR／線性資料沿原交付追溯，不複製數十 GB，不宣稱本次重新渲染或重新檢查全部 EXR 像素 |
| 全屋共享母檔與局部修形／材質細化 | 不重新執行上游 Python、修形、材質或燈具作業；原 SKP、prepared BLEND 及 Studio 修訂不變。另標示 render_copy_modified=true、preserved=false，不能把它冒充與原 prepared 幾何／著色器完全相同 |
| 沉浸導覽、燈光配對、比較頁 | 抽取新版 gallery／tour 程式，將 URL 改為相對路徑；沿用已確認的相機、12 條路線及比較資產。新原模型試圖只提供鏡位跳轉按鈕，不捏造門口熱點 |
| 4K 先可操作、8K 延後升級 | 保留 GalleryResources 的取消、串行解碼、8K 失敗／低 FPS 回到 4K、context 恢復。GPU 224 MiB、CPU 320 MiB；完整 mip chain 的 4K+8K 約 213.34 MiB，最多 8 倍各向異性取樣 |
| 可重現、來源及版本凍結 | 新 run 保留 source-request、操作規範文字快照、執行核心程式、上游驗收引用、圖檔 SHA 及新包自己的 release.json；原發布 hash 與新包 hash 分開 |
| 原子發布與回復 | 匯入完成最後才登記 source-site.json，失敗版本不取代可用成果；原站台與舊包保留。本機新包尚未自動公開發布，已發布上游的 HTTP／FPS 證據明示來源，不當成本次新包實測 |

## 合約與邊界

交付目錄目前支援 上游製作流程 實際使用的 `delivery.json`／`release.json`／`renders/gallery.json`／`tour-navigation.json` 契約。交付需要 passed、manifestSha256、releaseContentHash、archive、nativeMaster、reports；發布清單需要 fileSha256。必要證據缺漏、來源不同、路徑逸出、圖片改動、開關取景不一致時停止同步，保留上一版。

用戶端只看到可讀的版本與製作說明，技術檔案留在 run／選用比較頁。來源是已完成製作的明確綁定，不是任意匯入外部網站，也不執行 prompt 內的指令。`--prompt` 用於版本追溯，不能自行授權公開上傳。

新版資料／展示／交付同步已實作；新 SKP 的寫實材質細化、布料遮罩與全屋原生 EXR 製作仍需要該案自己的製作設定及實際視覺審查。本次沒有把既有 大型測試模型 修形名單或座標包裝成通用自動求解器。

## 驗證與重建

共用實作：`studio/production_site.py`、`site_packaging.py`、`site_validation.py`；展示來源雜湊見 `frontend/src/source-gallery/upstream.json`。`tests/test_production_site.py` 使用合成圖片與證據檢查來源錯誤、檔案改動、未通過審閱、路徑逸出與原件不變；`frontend/tests/source-gallery-resources.test.mjs` 驗證預算、解碼取消與 mip；`tests/integration/test_source_site.py` 另用真 Blender 檢查裝置、保留指紋與可部署包。

`site_validation.verify_http(url)` 只核對 HTTP 內容 SHA、導航及靜態引用，不能代替瀏覽器互動／FPS。新包的重新建置與程式改動仍需要本輪瀏覽器驗證，不能沿用上游的測量數字宣稱新版本已通過。

可由原交付及共用程式重建；新 run 不覆寫舊 run。正式交付另存案件 deliverables 並更新同案入口；原生母檔／線性資料沿原位置保留。
