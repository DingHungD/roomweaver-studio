# 三種匯入範例

此目錄只保留三個使用者入口，使用同一份 **Project04 教學衍生平面**。不包含原案件的私人來源檔；不是現行核准設計或施工圖。原始電子轉錄的來源雜湊保存在 `from-dxf/layout.json`。

| 想練習的流程 | 上傳檔案 | 預期結果 |
|---|---|---|
| [圖片辨識](from-image/README.md) | `from-image/project04-plan.png` | 真實 Agent 辨識、疑點確認、概念 3D；需要 Codex |
| [電子平面](from-dxf/README.md) | `from-dxf/project04-plan.dxf` | 69 個元件，確認單位／高度後建立概念 3D；不需要 Agent |
| [已有 3D](from-3d/README.md) | `from-3d/project04-apartment.glb` | 已有家具、材質與燈光的可編輯模型；不需要 Agent |

圖片與 DXF 建立的是概念模型，不會自動等同於第三套已配置家具的模型。圖片辨識也不會偷偷載入 DXF 或答案 JSON；同一張圖重辨識可能出現不同疑點，須依 UI 檢查結果確認。

## 直接從介面開啟

先依根 README 完成安裝。在 repo 根目錄啟動（以下命令使用已啟用的 Python 環境）：

```shell
python -m interior.workbench serve --workspace workspace
```

開啟 `http://127.0.0.1:8765/`，在「我的專案」按「＋新建專案」，選空白資料夾並確認名稱；進入「01 匯入」後點各卡片的「開啟範例」。點卡片主區域則開啟電腦的選檔視窗，可選自己的檔案或表中範例檔。

每次開啟在選定專案內建立獨立收件批次，不覆蓋原件或已保存設計。圖片範例僅載入 PNG，仍須按「請 Agent 辨識」，不會偷用 DXF 或預填辨識答案；DXF 範例進入平面確認；3D 範例複製原生 BLEND／GLB 配對，準備完成後進入編輯。工具重新開啟可點首頁的專案卡片續接。

## 所有者與重建

這三套檔案屬 repo 教學素材。平面資料權威位置是 `from-dxf/layout.json`，PNG／DXF 由 `from-dxf/build_plan.py` 產生；3D 由 `from-3d/build_example.py` 與附授權清單的素材產生。模型不是 Project04 原始 BLEND 的副本。

旧的合成案例已移至 `tests/fixtures/legacy-examples/`，只供回歸與歷史證據，不能直接刪除仍被測試引用的檔案。執行紀錄、Agent 回覆、截圖與匯入後產物屬 workspace／`artifacts/`，不加入可發布範例。
