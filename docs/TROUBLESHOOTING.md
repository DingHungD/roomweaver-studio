# 疑難排解

| 現象 | 處理 |
| --- | --- |
| 找不到 Blender | 執行 `roomweaver doctor`；設定 `INTERIOR_BLENDER` 為執行檔，再重啟服務 |
| frontend_not_built | 在根目錄執行 `npm ci --prefix frontend` 及 `npm run build --prefix frontend` |
| 找不到專案 | `init` 與 `serve` 指定相同 workspace；相對路徑從目前終端目錄解析 |
| 連接埠被占用 | 用 `serve --port 8875`；不要對同一 workspace 啟動兩個服務 |
| GLB 拒絕／物件對應失敗 | 確認是有效 GLB、節點與名稱清楚、尺寸正確；在 Blender 重匯出，勿僅改 SKP／PNG 副檔名 |
| 上傳過大 | 檔案上限85 MB，HTTP 請求另有 90 MB 邊界；先精簡網格或貼圖 |
| 黑圖被擋下 | 確認鏡位不在牆內、燈具另有真實光源；光影頁自動配置或新增光源，保存、重新確認後低解析出圖 |
| 3D 亮、Cycles 暗 | 材質展示有輔助光，光影預覽亦非完整光線追蹤；以實際試圖確認 |
| 不能建立出圖工作 | 按提示補觀看點、保存、確認編輯；不會暗中替使用者通過確認 |
| 修訂衝突 | 其他分頁／工作保存了新版，重新整理後重新套用修改；勿手改 revision 或雜湊 |
| 磁碟不足 | 低於 6 GiB 停止提交；備份後清理測試 workspace；UI 舊修訂清理僅移出列表、可恢復，不釋放磁碟空間 |
| Codex 啟動失敗 | 先確認原生 `codex.exe --version` 與 `app-server`，設定 `INTERIOR_CODEX` 並依官方說明登入，勿複製 token |
| 瀏覽器測試失敗 | 安裝 `.[agent]` 及 `python -m playwright install chromium`，檢查任務與實際截圖證據 |
| 重啟後 interrupted | 看工作日誌、核對設定後建新工作，勿手動改 completed |

工作證據位於 `workspace/projects/<id>/runs/interior-studio/<job>/`；佇列狀態在 `workspace/artifacts/workbench/local/`。回報時提供合成輸入、版本及必要錯誤摘要，先移除私人路徑和客戶內容。
