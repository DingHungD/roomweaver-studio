# Contributing

依 README 建立獨立環境。本 repo 只包含共用功能及合成範例；workspace 是使用者資料，不進版本控制。

1. 建分支，描述問題與預期行為，使用自製合成輸入。
2. UI 修改在 `frontend/`，API／資料在 `src/interior/workbench/`，渲染在 `src/interior/visualization/`。
3. 跑 Python、前端測試及建置；改渲染時另跑合成 Blender 與 smoke。普通資料測試不呼叫付費模型。
4. 更新操作文件；格式修改要兼顧舊 revision、checkpoint 和結果，不能手改現行資料繞過檢查。
5. PR 說明行為、測試與未驗證事項，圖像品質另做人工判讀。

更新依賴時同步 constraints／npm lock 並重新驗證。提交前檢查 `git diff --cached`，不可包含認證、真實案件、DB、node_modules 或虛擬環境。貢獻採本 repo MIT，外部素材須注明來源及授權。
