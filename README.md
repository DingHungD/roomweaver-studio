# Roomweaver Studio

Local interior editing, lighting and Blender rendering — 本機室內模型編輯、光影配置與全景出圖工作室。

將 **GLB 匯入 → 編輯物件／材質／光影／觀看點 → Blender Cycles 出圖** 串成瀏覽器介面。檔案與渲染留在自己的電腦；基本流程不需要 API key、Codex 或模型訂閱。

**早期開發版，介面為繁體中文。** 完整驗證環境：Windows、Python 3.11.9、Node.js 24.19.0、Blender 4.5.14 LTS。其他作業系統尚未完成端到端驗證。

![日光公寓的實際 Cycles 渲染](examples/daylight-apartment/preview-living.png)

上圖使用隨附日光公寓、BlenderKit 免費 CC0 家具與貼圖，經 Cycles 實際渲染。窗外為示意城市環境，非基地照片。完整光影用 native Blender／GLB 配對重現；單獨 GLB 不保留 HDRI world。

## 功能與格式

- 匯入 GLB，保留原件，建立工作副本。
- 在 2D 平面或 3D 選取整組家具；單物件展示可選子物件，修改基本色、粗糙度及材質需求。
- 移動／刪除家具、配置或綁定光源、預覽近似光影。
- 拖曳觀看點、設定多個效果圖方向與雙向連結。
- 確認後產生 2:1 全景及透視效果圖，保存修訂、工作日誌及舊成果。
- 選用 Codex App Server 執行材質候選、試圖判讀及受控瀏覽器能力測試。

| 輸入／功能 | 本版狀態 |
| --- | --- |
| `.glb` | 可直接匯入；建議嵌入貼圖、清楚命名物件，以公尺校核尺寸 |
| `.png`／`.jpg` | 僅作外部建模參考；**尚不能直接轉成可編輯 3D** |
| `.dwg`／`.dxf`／`.dwf`／`.skp` | 尚未提供直接入口；先用支援該格式的建模軟體整理並匯出 GLB |
| 燈具模型 | 網格外觀不等於光源，需另有實際光源資料或在光影頁新增 |
| 材質連結 | 保存參考網址與描述；候選採用目前修改基本色與粗糙度，不是完整 PBR 下載器 |
| 觀看點連結 | 保存導覽關係；尚未產生移動影片或完整公開導覽網站 |
| Claude／Ollama | 尚未實作 adapter |

## 安裝需求

| 工具 | 版本／用途 |
| --- | --- |
| Git | Clone 原始碼 |
| Python | 建議 **3.11.x**；宣告接受 3.11–3.13，其他版本未完成同等驗證 |
| Node.js／npm | **24.x**，用於建置及前端測試；建置後不需 Node 常駐 |
| Blender | **4.5 LTS**，須能執行 Cycles |
| 瀏覽器 | 支援 WebGL 的近期桌面瀏覽器 |
| 磁碟 | 渲染所在磁碟至少 6 GiB 可用空間，並預留修訂及圖片空間 |

CPU 可以渲染；相容 NVIDIA GPU 會嘗試 OptiX，否則使用 CPU。大型模型的記憶體與時間取決於場景。本 repo 不附 Blender 安裝包。

## 從 clone 到啟動（Windows PowerShell）

命令都在 repo 根目錄執行。

```powershell
git clone https://github.com/DingHungD/roomweaver-studio.git
cd roomweaver-studio
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-lock.txt -e ".[dev]"
npm ci --prefix frontend
npm run build --prefix frontend
```

安裝 Blender 後，將以下路徑換成自己的 **blender.exe**；若已在 PATH 可省略環境變數。

```powershell
$env:INTERIOR_BLENDER = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
.\.venv\Scripts\roomweaver.exe example --workspace workspace
.\.venv\Scripts\roomweaver.exe doctor
.\.venv\Scripts\roomweaver.exe serve --workspace workspace
```

開啟 **http://127.0.0.1:8765/**。`example` 登記完整日光公寓；到匯入頁選 DAYLIGHT 並點「使用案件現行模型」。它不自動確認設計或出圖。若只想建立空案件，改用 `init`。這些命令不需啟用 PowerShell 虛擬環境腳本。

每次重新開終端須重新設定 `INTERIOR_BLENDER`，或把 Blender 加入自己的 PATH。下次啟動只需設定路徑再執行 `serve`，不需重裝或重新匯入。8765 被占用時改成 `serve --workspace workspace --port 8875`，開啟 http://127.0.0.1:8875/ 。不要同時用兩個服務開啟同一份 workspace。

`requirements-lock.txt` 是已測試環境的 **constraints**，用 `-c` 限制版本。基本安裝不會因此安裝全部選用 Agent 套件。

## 第一次操作：日光公寓

[完整範例與資產來源](examples/daylight-apartment/README.md)包含免費 CC0 沙發、茶几、兩張木椅與床，以及木紋、布料、灰泥貼圖和城市 HDRI。另有窗簾褶皺、棉被垂邊、枕頭、櫃門接縫與陽台近景幾何。

1. **匯入**：選擇 Daylight apartment · DAYLIGHT，點「使用案件現行模型」。這會建立原生 `.blend`／GLB 工作副本，保留 HDRI、面光與材質。
2. **材質**：選沙發或椅子，雙擊進入單物件展示以檢視子物件。首次重現範例請保留原材質：目前「基本色」指派會替換該子物件的材質，包含原貼圖；不是保留 PBR 通道的調色器。
3. **光影**：可直接保留現有日光。要微調時點「自動配置照明」，取得現有光源，保存後用 3D 光影預覽檢查。第一次不要啟用 Codex 判圖。
4. **觀看點**：已附 Living、Bedroom，各有一個 32 mm 方向及雙向連結。可拖曳位置、修改方向，再用「3D 預覽」檢查。
5. **確認**：點「確認編輯，前往整合輸出」。
6. **出圖**：先選低解析，點「建立出圖工作」，核對 **2 張全景＋2 張效果圖**，再點「確認並開始渲染」。人工檢視後才提交正式尺寸。

預覽為 1024×512 全景、640×480 效果圖；正式為 4096×2048 全景、1600×1200 效果圖。README 示意圖是範例腳本的 1440×1080、96 samples Cycles 出圖。改動後須保存並重新確認，舊成果會標示舊修訂。

2D 用方向鍵／WASD 平移、滾輪縮放；3D 用 W/S 前後、A/D 水平側移、空白鍵／Shift 升降。雙擊物件進入單物件展示、拖曳旋轉；操作時先將焦點放在畫布。

2D 是不受場景光照影響的材質平面，保留家具基本色與貼圖；「平面辨識模式」另將地板簡化並加上輪廓。一般 3D 編輯使用獨立補光，光影頁使用已採用的燈光設定預覽，避免 GLB 內高強度日光重複疊加。這些顯示設定不改動原材質、光源或 Blender 出圖結果。

也可直接上傳 [daylight-apartment.glb](examples/daylight-apartment/daylight-apartment.glb)，但 GLB 僅使用窗外近似燈光，不能重現完整 HDRI。要得到上圖的光影，請用上述配對入口。

保留的 [輕量範例](examples/demo-apartment/README.md)僅作安裝與自動測試 fixture，適合很快測試 GLB 上傳，不是品質展示。

## 使用自己的檔案

先停止服務（Ctrl+C），建立另一案件，再用同一 workspace 啟動：

```powershell
.\.venv\Scripts\roomweaver.exe new-project MY_HOME --name "My home" --workspace workspace
.\.venv\Scripts\roomweaver.exe serve --workspace workspace
```

在案件選單選新案件，匯入自己的 GLB。ID 使用英數、底線或連字號，顯示名稱可以不同。

先在建模軟體確認尺寸、法線、牆厚、家具名稱及貼圖。名稱／階層與幾何只是分組線索，匯入後仍應檢查；房間不保證能從任意網格自動準確辨認。建議物件名稱清楚且不重複。

原件複製到案件 `sources/`；Blender 工作模型與成果寫入 `runs/`；修改採不可變修訂，不回寫你選取的原始 GLB。大小限制見 [疑難排解](docs/TROUBLESHOOTING.md)。

## 選用：Codex Agent

完成基本流程後才需要此項。安裝額外套件及瀏覽器：

```powershell
.\.venv\Scripts\python.exe -m pip install -c requirements-lock.txt -e ".[agent]"
.\.venv\Scripts\python.exe -m playwright install chromium
```

依 [官方 Codex CLI 說明](https://developers.openai.com/codex/cli) 安裝並登入自己的帳號，確認 CLI 提供 `app-server`。Windows 請把 `INTERIOR_CODEX` 指向原生 `codex.exe`，不要指向 npm 的 `.cmd` 包裝檔。例如 `$env:INTERIOR_CODEX = "C:\path\to\codex.exe"`，然後重啟服務。

UI 開啟「Agent 與能力測試」，分別檢查連線、看圖、工具、瀏覽器操作。使用 [App Server stdio 協定](https://developers.openai.com/codex/app-server)，adapter 原先針對 CLI 0.154.0 撰寫；新版需再驗證。**本次獨立版尚未執行真實訂閱／模型測試。**

Codex 使用雲端模型與帳號額度，不是完全離線推論。啟用判圖會傳送試圖及任務所需資訊。憑證由 Codex 管理，不寫入 repo。失敗不自動切換其他付費供應者。Computer use 目前為專用 Playwright 瀏覽器與受控工具，不是控制整個 Windows 桌面。

## 開發、測試與打包

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m build --wheel
```

測試不呼叫雲端模型。真正 Blender 驗證需設定 `INTERIOR_BLENDER`：

```powershell
.\.venv\Scripts\python.exe tools/smoke_render.py --workspace artifacts/smoke-my-run
.\.venv\Scripts\python.exe -m pytest tests/integration/test_blender_checks.py -q
```

Smoke 目錄須尚未存在；它會上傳範例、確認修訂並產生四張真圖，保留證據。不呼叫 Agent。詳見 [驗證紀錄](docs/VALIDATION.md)。

開發時先啟動 8765 後端，再於另一終端執行 `npm run dev --prefix frontend`，開啟 http://127.0.0.1:5173/ 。一般啟動由 FastAPI 提供已建置頁面。

Wheel 包含 Python 核心、Blender 腳本與建置好的 UI；範例和開發文件留在 repo。**打包前必須建置前端。**

## 檔案與資料管理

```text
frontend/                         React + TypeScript + Three.js
src/interior/workbench/            API、案件、工作佇列
  studio/                         場景、修訂、材質、燈光、觀看點
  orchestration/                  LangGraph 確認／續跑
  agent_runtime/                  Codex 與受控工具（選用）
src/interior/visualization/        Blender／Cycles 與畫面檢查
examples/daylight-apartment/       CC0 家具／貼圖、GLB/native 配對、渲染圖
examples/demo-apartment/           最小測試 fixture
tests/                            單元、契約及合成 Blender 測試
tools/                            開發者驗證工具
docs/                             架構、驗證、疑難排解
workspace/                        執行後建立；私人資料，不進 Git
```

`workspace/artifacts/workbench/local/jobs.sqlite3` 管工作與事件；`agent-checkpoints.sqlite3` 管 LangGraph 狀態。案件設定、原件與大檔案在 `workspace/projects/<id>/`。使用 SQLite，不需另架 DB 服務；備份與恢復見 [架構文件](docs/ARCHITECTURE.md)。

本版為本機單使用者，僅綁定 loopback，尚無公開部署的帳號與隔離機制。架構改進見 [架構評估](docs/ARCHITECTURE.md#下一階段優化)。

## 授權與參與

程式與原創場景組合採 [MIT](LICENSE)；日光公寓中的第三方資產保留 CC0-1.0。第三方套件各自保留授權，見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。匯入的私人模型及素材不會因此變成 MIT。

參與方式見 [CONTRIBUTING.md](CONTRIBUTING.md)，安全範圍見 [SECURITY.md](SECURITY.md)。勿提交客戶資料、憑證、workspace 或私人日誌。
