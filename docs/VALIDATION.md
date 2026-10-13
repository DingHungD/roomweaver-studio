# 獨立版驗證紀錄

## 2026-10-13 本階段發布檢查

本次整理包含三種匯入範例、牆地群組、用途與尺寸来源防錯、材質 UV／預覽修正、配置三分頁、Agent 概念家具，以及指定候選的有界錯誤修正。下方較早紀錄中的「本機／未推送」描述當時狀態；本節為本次發布範圍與驗證依據。

| 檢查 | 結果 |
| --- | --- |
| 完整 Python 單元／契約回歸 | 246 通過；不呼叫雲端 Agent |
| 前端回歸 | 73 通過 |
| TypeScript、正式 UI 建置 | 通過；既有 bundle 大小提醒仍在 |
| 真實 Blender 4.5.14 整合 | 17 通過，另 2 個 subtests 通過；含建模、交接、替換、材質、出圖、尺寸改造與原件保全 |
| Python 依賴一致性 | 通過 |
| 全新建置目錄的 wheel、獨立目錄安裝 | 通過；從安裝包啟動，頁面、JS/CSS、案件 API 及關閉流程通過 |
| 發布資料 | 範例素材／產物 SHA-256、文件連結、Git 差異檢查通過；不納入私人 workspace、Agent 輸出、下載模型或憑證 |

完整回歸初次發現兩個舊測試假設失效，修正後重測：直接連結測試不再以清單第一組充當家具，改為明確選取沙發；模型清單測試分開驗證 DXF 支援家具與編輯器完整家具／裝飾／燈具清單，不放寬 DXF 格式或用途防錯。兩張公開範例 PNG 移除本機來源路徑中繼資料，像素不變，manifest 雜湊同步更新。

### 本阶段真實操作與限制

- 前一輪使用相同 UI 工作流完成 6 件未配置家具的 Agent 概念建模，均經第二版碰撞修正後採用；必要家具與已確認規格保留。這些是概念模型，不代表精細商品或施工驗收。
- 指定衣櫃的「選擇並替換」實測通過：同一候選自動選擇水平適配方向後，尺寸約 53 × 160 × 220 cm，通過碰撞並保存新修訂。另 30 個群組、原件雜湊及需求保持不變。此件第一版即成功，不能算成 Agent 錯誤修正分支的端到端實測。
- Agent 分支另以合成碰撞案例測試真實 Codex 回覆，配合共用幾何檢查通過；真實 Blender 的縮放、固定方向、确认尺寸及原件保全由獨立整合測試覆蓋。本次發布檢查沒有再執行雲端配置或修改使用者場景。
- 目前示範案件仍有一項先前牆面素材配對因未查核／重複素材回覆而待處理；不得把套件測試通過當作整案全部完成。任意模型的材質、使用側與實際生活動線仍需預覽確認。
- 原始模型與歷史模型未清理。既有 ezdxf 棄用提醒與前端 bundle 大小提醒尚未消除，不阻擋本次測試／建置。

重跑：`python -m pytest -q`、`npm test --prefix frontend`、`npm run build --prefix frontend`；設定 `INTERIOR_BLENDER` 後另執行 `python -m pytest tests/integration -q`。套件建置使用 `python -m build --wheel`，建議於全新 checkout 執行，避免舊 build 暫存混入歷史前端檔案。GitHub CI 執行一般回歸、前端與 wheel；Blender 和真實 Agent 檢查在本機執行，兩者不混稱。

## 2026-10-12：三種 Project04 教學衍生範例

現行入口見 [範例手冊](../examples/README.md)。舊合成案例移到 `tests/fixtures/legacy-examples/`，同步測試、smoke 工具與文件引用；移除被替代的舊日光公寓模型及圖片，保留 CC0 原素材。

- **DXF 真實 UI 匯入**：69 個元件；透過右側 UI 填入來源表的牆厚／家具高度、確認建模，進入 02 編輯。69 個網格的 GLB／BLEND 對照與空間檢查通過。
- **GLB 真實 UI 匯入**：25.46 MB，67 個單物件／157 個組成；進入 02 編輯並切換 2D／3D。157 個網格交接檢查通過，貼圖無遺失。原生範例腳本另完成 1200×900、48 samples Cycles 預覽；GLB 不含 HDRI，兩者不能視為相同照明品質。
- **PNG 真實 Agent 與 UI 匯入**：GPT-6.1-Sol 整圖／放大複核辨認 24 個家具區域、5 個門洞與 5 個窗洞，留下 4 題。依生成來源在 UI 答覆並請 Agent 修正後，仍缺兩個加厚柱體；使用既有「＋牆體／精確頂點」UI 補繪，沒有修改後端案件 JSON。確認後生成 70 個網格，交接檢查通過並進入 02 編輯。此項不是全自動辨識通過，尺寸與平面形狀仍是概念還原，未驗收為精確 CAD 或施工圖。核對資料與人工操作見圖片範例手冊。
- **一般檢查**：8 項相關 Python 測試、前端正式建置通過；原生配對登記命令可用。素材與產物雜湊、文件連結、Project04 原生模型未變動均核對通過。單檔最大 31.10 MB。

本機預覽案件：`EXAMPLE_IMAGE`、`EXAMPLE_DXF`、`EXAMPLE_GLB`，位於既有測試服務 8876 的 workspace。截圖與驗證資料在忽略追蹤的 `artifacts/examples-project04/`。三条匯入完成不等於三個案件均完成最終渲染或人工設計驗收；本輪未上傳 GitHub。

日期：2026-10-10。範圍：Roomweaver Studio 本機首次抽離版本。環境：Windows、Python 3.11.9、Node.js 24.19.0、Blender 4.5.14 LTS。

| 驗證 | 結果 |
| --- | --- |
| 新建 Python venv、安裝基本／dev 套件 | 通過 |
| npm ci、TypeScript 檢查、Vite build | 通過；bundle 大小警告仍存在 |
| Python 單元／契約測試 | 37 通過，含範例原件保全、雜湊及路徑拒絕 |
| 前端測試 | 37 通過，含 PBR 材質還原、日光隔離、室內取景、柔光及牆體切面 |
| Blender 整合套件 | 10 通過，另有 2 個 subtests 通過 |
| 真實 API smoke | 匯入 GLB → 保存 → 確認 → 渲染 → 完成；2 張全景、2 張效果圖，尺寸與品質檢查通過 |
| 瀏覽器操作 | 新 DEMO 空白匯入 → 編輯；椅子分為兩組、各 6 子物件；照明提案找到 2 燈、保存成功，Codex 判讀關閉 |
| Wheel 建置與安裝 | 另一個全新 venv 安裝 wheel，包含 UI、Blender 腳本與授權；未安裝 Agent extras 仍能提供頁面及案件 API |
| 依賴一致性 | pip check 通過 |
| 發布檔案檢查 | Git 清單未含 runtime、原案件、已知私人路徑或典型憑證字串；並非完整安全稽核 |

![實際匯入並保存照明的介面](images/studio-lighting.png)

合成模型出圖見 [效果圖](../tests/fixtures/legacy-examples/demo-apartment/render-preview.png)。人工目視確認該圖有照明與家具，並未把簡單幾何評為照片級成果。

本機詳細證據位於被 Git 排除的 `artifacts/`，包括 smoke 報告、Blender 工作結果、wheel 安裝與檢查紀錄。可依根 README 的命令重新生成；這些私人機器日誌不隨公開 repo 發送。

未驗證：獨立版真實 Codex 訂閱／雲端模型與 browser Agent、4096×2048 正式品質、異機完整資料恢復、Linux／macOS 全流程、大型外部模型。GitHub Actions 的首次遠端結果以 repository Actions 頁為準。API smoke 與瀏覽器操作為分開的驗證，並非全套 UI 自動化測試。

## 日光公寓增補

2026-10-10：9 項免費 CC0 BlenderKit 資產（4 家具、4 材質、1 HDRI），來源與 SHA-256 在範例 assets/manifest.json。GLB 含 26 張嵌入圖片、228 個網格。原生場景生成兩張 1440×1080、96 samples Cycles 圖，人工目視修正牆面及布料比例。

原生配對另經完整應用 smoke：匯入 → 修訂 → 確認 → 2 張全景＋2 張效果圖成功，未呼叫雲端模型；詳細證據保留在本機 artifacts/daylight-smoke-v1。GLB 單檔另含點錐光近似，不宣稱保有 HDRI world。

## 編輯平面泛白修正

日光公寓的 GLB 日光強度約 1229，原先與編輯補光疊加造成泛白。2D 改用不受光照及曝光影響的基本色／貼圖；一般 3D 編輯隔離匯入燈光，光影頁繼續使用採用設定建立預覽。原件、案件修訂與 Cycles 渲染未更動。

29 項前端測試及正式建置通過。以既有日光公寓 smoke 工作區實際開啟瀏覽器，核對平面辨識開／關、床的選取框、單物件展示及返回 2D，無頁面執行錯誤；截圖保留在本機 artifacts/plan-*.png。本輪沒有重新渲染。

## 室內取景與 B 柔光平面

新增室內地板範圍取景；2D 隱藏鄰棟、陽台與切面上方物件，取景及點選使用同一裁切範圍。缺少可辨識地板時退回剩餘模型邊界。32 項前端測試、建置及日光公寓瀏覽器檢查通過：2D 置中放大、切換 3D 可見鄰棟、返回平面及案件修訂不變。證據在本機 artifacts/plan-style-study-v1。

使用者選定 B 後，已實作成即時 WebGL 柔光平面：PBR 貼圖保留、固定曝光、四個分散方向的陰影取樣、水平牆體封口與室內自動取景。四張 1024×1024 陰影圖在設計、選取或模式變更時更新，縮放平移不重新計算陰影。原生模型及既有整合輸出不修改。

37 項前端測試及建置通過，涵蓋貼圖引用與原材質恢復、陰影裁切、光照上限、牆體旋轉／位移及中空切面保留。日光公寓瀏覽器檢查與截圖在本機 artifacts/plan-b-release；README 展示實際 WebGL 畫面，不以離線 Blender 提案圖代替產品畫面。未重跑 Blender 正式渲染及雲端 Agent；本次修改僅前端預覽。


## DXF 平面確認與共同交接（2026-10-11，本機）

- Python 單元／契約測試：46 通過。新增尺度／旋轉、門窗宿主與高度、非凸／非平面與未支援內容、過期確認、重送去重、原件雜湊、平面備份還原及交接身份檢查。
- 前端既有回歸：37 通過；TypeScript／Vite 正式建置成功，約 1 MB 的 bundle 警告仍存在。pip check 通過；ezdxf 的 pyparsing 棄用警告不影響測試結果。
- 真實 Blender：`tests/integration/test_plan_pipeline.py` 通過。合成 DXF → BLEND／GLB → 初始修訂 → 保存觀看點 → 1 張全景＋1 張效果圖；光照檢查通過。射線核對門洞、窗洞、鄰牆、窗台與門楣。故意偏移 GLB 後交接被拒絕。證據在本機 `artifacts/dxf-validation-final/`。
- 原生／GLB 照明差異回歸：1 項測試、2 子項通過。既有日光公寓另實跑交接：228 個網格對應通過，沒有重新產生其正式渲染。
- 瀏覽器實跑上傳範例、保存檢查、勾選確認、建模、自動跳轉 2D／3D 編輯，無頁面執行錯誤。另核對重新開啟可續編平面。畫面與本機測試 workspace 在 `artifacts/dxf-ui/`。
- 未執行雲端 Agent、PNG 辨識、DWG／SKP 匯入、4K 正式出圖或新版本跨機安裝。DXF 概念模型不是寫實家具品質驗收。

新增測試可用 `python -m pytest tests/integration/test_plan_pipeline.py -q` 重跑；須先設定 `INTERIOR_BLENDER`。預設 `pytest` 不執行 Blender 整合測試。


## 通用圖片確認、配置與概念家具（2026-10-11～12）

公開驗證使用合成輸入。案件原圖、需求、確認紀錄、Agent 對話及個案分析留在本機，不隨 repo 發布。

- 圖片上傳與辨識分開；候選具原圖座標、數字登錄及待確認問題。支援放大複核、確認來源輸入、原圖 A→B 答覆、依證據修正與版本追溯。
- 已確認數字優先於手繪筆畫比例。直角校正及尺寸套用只接受明確端點；未知端點與衝突保留，不為閉合而改數字。首次辨識、複核與答覆後修正共用此原則。
- 自動修正有範圍與次數限制；拒絕未知引用、越界、過期版本、未確認尺寸覆蓋與重複副作用。部分回答不自動關閉整題。
- AI 空間配置保存需求、家具區域、操作區與生活動線。修正不可刪除必要家具或改動固定基線；碰撞與漏件仍阻擋採用。允許明確接受部分動線限制後進入概念編輯，並不等於設計驗收。
- 編輯頁可新增十類概念家具，支援移動、子物件材質、刪除、復原、保存重開及 Blender 出圖。

### 已執行的真實 Agent 與 UI 驗證

以下是開發期間的獨立驗證，本次發布前沒有重新呼叫雲端模型。

- 合成 6 × 6 m 工作室：Codex 首輪候選引用不存在的家具，被拒絕後下一輪修正成功；提出工作桌及兩條動線。瀏覽器採用並建立概念 3D，桌子維持父子物件分組。範例見 [layout-study](../tests/fixtures/legacy-examples/layout-study/README.md)。
- 兩張獨立合成手繪圖：真實 Codex 訂閱／GPT-6-Astra 辨識後各有四題，依各自答案生成新版後無剩餘辨識疑點。第二張圖曾因越界被拒絕，改善通用提示後明確重送通過，未放寬驗證條件。範例見 [hand-drawn-study](../tests/fixtures/legacy-examples/hand-drawn-study/README.md)。
- 第一張圖完成家具區域提案、圖上答覆、重新提案與概念建模；第二張圖於 UI 新增椅子、復原、保存及修改座面材質。重啟服務／頁面後修改仍保留，原始模型雜湊不變。
- 圖內滾輪不捲動頁面；答覆與 A→B 可保存重開；匯入面板分段、已確認資訊收合及建模阻擋原因以實際瀏覽器操作核對。

這些是小型合成案例的技術驗證，不代表任意手稿辨識正確率、完整住宅設計、施工尺寸或寫實品質保證。UI 操作、模型執行、幾何檢查及人工判圖分別記錄，並非完整 UI 自動化覆蓋。此階段尚未包含 BlenderKit 自動找模組／替換；後續本機驗證見下方專節。

### 2026-10-12 發布前重新執行

| 檢查 | 結果 |
| --- | --- |
| Python 單元／契約測試 | 126 通過 |
| 前端測試 | 47 通過 |
| TypeScript 與 Vite 正式建置 | 通過；既有 bundle 大小警告仍在 |
| 真實 Blender 整合 | 2 通過：DXF 建模／洞口／交接／新增家具出圖；全部概念家具類別交接 |
| Wheel 建置、依賴一致性 | 通過 |

發布整理另移除四張既有範例 PNG 的本機來源路徑中繼資料，像素逐一核對不變，相關 manifest 雜湊同步更新；不改動範例模型或渲染效果。

Blender 整合實際產生 BLEND／GLB、1 張全景與 1 張效果圖，核對新增家具材質及原件雜湊，並驗證偏移 GLB 被共同交接檢查拒絕。它不是正式高解析或照片級驗收。ezdxf 的 pyparsing 棄用警告仍在。

重跑方式：`python -m pytest -q`、`npm test --prefix frontend`、`npm run build --prefix frontend`。設定 `INTERIOR_BLENDER` 後，可另跑 `python -m pytest tests/integration/test_plan_pipeline.py tests/integration/test_layout_models.py -q`；一般測試不呼叫雲端 Agent，也不執行 Blender。

## BlenderKit 單物件配對（2026-10-12，本機新增）

- 本輪後端回歸 136 項通過，再增補 2K 套件選擇案例；素材專屬測試涵蓋真實候選 ID、免費排序、價格／版本／授權變動、陌生下載來源、容量上限與半成品清理、憑證不送 CDN、配對及工作去重、物件變動後拒絕舊候選、材質目標、GLB 尺寸轉換及付費確認。
- 47 項前端回歸與 TypeScript／Vite build 通過。配對面板另以真實瀏覽器操作驗證，沒有把既有前端單元測試當作完整新介面覆蓋。
- `tests/integration/test_asset_replacement.py`：真實 Blender 完成概念椅 → 家具模型 → 指定子物件材質 → 全景及效果圖，核對 GLB／BLEND 交接、原件雜湊、組別／位移／燈具綁定、其他物件及受控還原。使用公開 CC0 範例素材，測試不呼叫網路或 Agent。
- 真實 Codex 與 BlenderKit：合成餐椅搜尋免費／付費候選，實際下載免費模型。UI 另完成免費 CC0 餐椅的下載、替換及重開，來源網址仍顯示；免費 CC0 木紋材質的 Agent 配對與 2K 套件下載／指定子物件套用經實際 API 完成。未使用私人住宅資料，未測試付費帳號購買／授權，也不執行自動購買。
- 程序材質的 GLB 與 Cycles 表現、完整貼圖尺度與寫實品質仍需人工核對。本機證據位於忽略的 `artifacts/asset-matching-live/` 與 `artifacts/asset-matching-test/`。未推送此次功能。

### 一鍵配置、儲存清理與旋轉（2026-10-12，本機）

- Python 回歸 142 項通過；最後路徑邊界調整後再跑 16 項素材／批次專屬案例通過。50 項前端測試、TypeScript 與正式建置通過，既有 bundle 大小警告仍在。
- 合成測試覆蓋整屋／房間／類型範圍、逐物件取消全局風格、图片上限與清除中繼資料、批次去重、中斷後狀態、單項失敗繼續、替換其他物件後候選仍有效及目標變動後拒絕。
- 清理測試核對使用中工作暫緩、只刪已取代 replacement、保留現用模型與原始匯入、重複清理冪等、已清理版本不能恢復保存或重新提交出圖。
- 真實 Blender 整合 1 項通過：概念家具旋轉 45°、替換家具及指定材質、全景／效果圖出圖、來源雜湊不變、舊替換模型實際刪除與舊版還原拒絕。測試無 Agent／網路呼叫。
- 真實 UI＋Codex：上傳合成北歐色卡及文字，單椅配對回傳 4 免費／2 付費候補，從結果進入正確單物件。另透過 API 啟動雙目標批次：地板取消全局風格後搜尋深色木地板（未送圖片），餐椅沿用共用文字與圖片；兩者皆完成，結果依各自輸入產生。
- UI 檢查水平旋轉 90°及復原；前端幾何測試驗證旋轉中心、非累積變換、光源位置與方向。試用案清理 API 實際釋放約 154.1 MiB，仍保留現用版本與兩筆來源連結。
- 未測試超大型整屋批次、付費帳號下載或自動整屋採用。圖片僅是風格提示，沒有把參考圖當作商品／尺寸驗證。本次未推送 GitHub。


### 自動第一版與確認後清理（2026-10-12）

新增 `tests/test_asset_automation.py`：全目標處理、免費失敗 fallback、固定操作 ID 重播、付費不得自動下載、修訂衝突暫停、同清單備選繼續使用、子物件分類及確認後清理範圍。單元測試不呼叫模型。後端 148 項通過；前端既有 50 項通過，TypeScript／Vite 建置通過。真實 Blender 替換／材質／出圖整合 1 項通過，確認 adopt 不再立即清除舊模型。

另以獨立合成 AUTO_PLACEMENT 案件完成真實 Codex＋BlenderKit＋Blender 串接：兩椅與一地板，3/3 自動替換；備選與最終清理另保留本機測試紀錄。這是工具串接驗證，不代表任意房屋的所有家具皆有合適商品，也不代替人工尺度、風格及動線驗收。證據存忽略目錄 `artifacts/asset-matching-live/`，不發布私人工作區或下載模型。

### UI 可重現的照明與裝飾（2026-10-12）

- 新合成 STAGING_HOME 案件，從 UI 匯入、配置、下載、採用、確認編輯到試圖，未以外部腳本修改其場景修訂。fixture 僅產生原始測試模型；服務重啟不重複下載。
- 真實 Codex／BlenderKit／Blender：2 盞免費 Travertine Ceiling Light、1 件免費 Dandelion glass vase flower、1 件免費沙發採用成功。照明初次查無可用候選，修正通用尺寸政策後透過 UI「只重試未完成項目」完成；不能把初次失敗寫成一次全通過。
- 沙發首個候選因適配後高度不足而拒絕，批次自行嘗試下一個免費候選並採用。沒有外部手動換模型。候選連結保留，未確認清理。
- 真實 UI 提交 Cycles：1 張 1024×512 全景、1 張 640×480 效果圖完成，照明試圖一輪通過。合成場景只有一面牆，不作完整住宅品質、窗戶採光或天花量測驗收。
- 修正最後一件完成時畫面仍留概念占位的更新競爭；真實 UI 沙發完成後自動切到新修訂。新增非同步回歸測試保護完成順序及未保存編輯。
- 後端相關 62 項、前端 54 項、真實 Blender 離線整合 1 項通過；另有生成名稱分類回歸。TypeScript／Vite 建置通過，既有 bundle 大小警告仍在。本機證據為 `artifacts/staging-ui/`，無 GitHub 推送。
- 配置為模型範圍＋名稱用途規則，Agent 為素材檢索／比較。任意新圖辨識品質、全屋家具語義、窗戶開口、精細表面支撐及動線仍須另驗；不宣稱此測試保證每案全部匹配或寫實品質。

## 2026-10-12 manual furniture/decor additions (local)

Synthetic `MANUAL_ITEMS` UI validation: 2D rectangle → chair prompt → six live Codex/catalog candidates; table rectangle → editable 0.75m support height → official free BlenderKit link → download/Blender replacement/adoption. Moving, horizontal rotation, soft deletion/undo and reopening preserved the source and decor classification. No Project03-specific script or direct scene patch was used. The chair search and vase replacement are separate checks; no final render or room-layout approval is claimed.

28 backend tests (`test_asset_links`, `test_asset_matching`, `test_staging`, `test_asset_automation`), 56 frontend tests and production build passed. Local evidence: `artifacts/manual-addition-ui/README.md`; runtime binaries and real service outputs remain excluded from Git. New link rejection tests cover non-official URLs, wrong asset type, stale revisions, operation reuse and explicit download authorization.

## Compact decor and lighting action rows (local)

59 frontend tests and the production build passed. Real UI actions in synthetic MANUAL_ITEMS: one-click decor automatically expanded and installed 1/1 asset; one-click lighting installed 2/2 ceiling fixtures and created three actual lights including sunlight. Manual light add and Undo restored the prior scene. Collapsing the panel retained processing, and the completed lighting batch synchronized its final revision. Evidence is local at `artifacts/compact-editor-ui/`. No final render, customer-scene edit, cleanup or GitHub push in this check.

## 2026-10-12 統一牆地分組與材質配置

- 三個 Project04 教學入口：原始圖片建模、DXF 建模與 GLB 案件均經共用整理 API 實測；DXF 整理按鈕以 UI 驗證。原模型 hash、子元件材質及家具保持相同，只建立新的群組修訂。
- 搜尋目標從圖片 70→31、DXF 69→31、GLB 96→37；牆地各一筆。是目標數，不是雲端延遲量測。
- 合成測試涵蓋分組、不同家具實例、房間限定範圍、子元件細調、候選來源、重複提交及舊案修訂保全。前端 73 項測試通過，正式 build 通過（仍有既有 bundle 大小提醒）。
- 兩項真實 Blender 整合測試通過：DXF 直線牆建模與開孔、整組材質替換、單段材質覆寫及渲染。沒有呼叫真實 Codex／BlenderKit 網路服務；資產使用 repo 的 CC0 檔案。
- 本機證據位於 `artifacts/structural-grouping/`，不納入公開 repo。通用重跑入口：`tests/test_structural_groups.py`、`tests/test_asset_*`、`tests/test_staging.py` 及 `tests/integration/test_asset_replacement.py`、`tests/integration/test_plan_pipeline.py`。
## 2026-10-12 Codex 模型選取修正

本機 CLI 0.154.0 的設定模型不在 `model/list` 中，導致未指定模型的素材配置繼承不支援名稱。現以清單預設模型明確啟動任務；指定模型必須通過清單驗證。一鍵配置先測試一次文字連線；權限拒絕中止整批，保留候選與模型，不當成零筆搜尋結果或繼續下載。31 項相關 Python 測試、73 項前端測試與 build 通過。透過本機 API 使用 `model=null` 實測解析為 `gpt-6-astra`，回傳 `STUDIO_READY`、狀態 passed；未重跑整屋配置或渲染。細節位於本機忽略的 `artifacts/codex-model-fix/README.md`。

## 2026-10-13 Blender 路徑與配置續跑

工作區可保存 Blender 路徑，服務重啟後讀取；下載前先檢查執行檔。缺少 Blender 時暫停整批，不耗盡所有候選，修正後沿用候選建立新工作、保留失敗紀錄。相關套件初測 18 項通過；新增舊版中途停止案例後，續跑與環境設定 12 項通過。前端 build 通過。真實 Blender 4.5.14 整合測試通過（23.70 秒），涵蓋家具替換、群組材質、子物件覆寫及兩張出圖；測試未重跑使用者整屋配置。證據在本機 `artifacts/codex-model-fix/README.md`。

## 2026-10-13 第二批自動修正（本機）

- 通用 UI 新增依失敗原因重新搜尋、允許區域內局部避碰，以及目前材質的本機預覽修正。每個目標最多兩輪重新搜尋；未知用途、環境錯誤與未授權移動不強行修正。
- 目前圖片範例透過真實 UI、Codex、BlenderKit 與 Blender 執行：17 組完成／14 項待處理變為 19 組完成／12 項待處理。新採用免費馬桶與洗手櫃；其餘原因逐項保存。沒有修改已確認尺寸、刪除必要家具或清理舊模型。
- 地板透過同一 UI 修正並採用四通道預覽，15／15 組成通過匯出 UV 檢查，實際 2D 預覽保留木紋。原生材質節點保留；本輪未重新渲染該住宅的正式高解析成果。
- 54 項相關後端、73 項前端、3 項真實 Blender 整合測試與正式建置通過。合成 Blender 場景驗證局部移動成功；真實案件未設定允許區域，只驗證碰撞攔截，不能當作全案動線驗收。
- UI 框選允許移動區域會回填世界座標，復原後回到原保存修訂。預設移動距離為零，需明確設定並保存才允許自動挪動。
- 本機證據：`artifacts/asset-repair-20261013/README.md`。沒有 GitHub 推送；外框碰撞、複合材質與任意素材語意仍有文件列出的限制。

## 2026-10-13 物件理解與規格預覽

43 項相關後端測試、73 項既有前端測試及正式建置通過。合成案件驗證尺寸與用途保全、過期修訂拒絕、方向推定、搜尋接收規格及原材質風格隔離。真實 UI 與 Codex 完成目前圖片範例 31 組規格複核，24 件家具中 22 件用途明確、2 件來源不足保留未知；現用修訂與模型未變。本輪未重新渲染或下載素材。證據存本機忽略目錄 artifacts/object-specifications-20261013；不依賴案件專用腳本、不推送 GitHub。
