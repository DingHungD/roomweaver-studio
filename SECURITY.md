# Security scope

支援本機單使用者、可信檔案的情境。Loopback、Host、Origin 與寫入 token 檢查不是公開部署的帳號認證。不要直接加公開隧道或對外綁定。

Blender 關閉自動執行腳本，輸出限定案件路徑，但 GLB 仍由原生解析器處理，沒有完整容器／作業系統沙箱；請勿匯入不可信檔案。

模型成功回覆不等於操作或安全驗證。憑證由 Codex 自行管理，永不提交到 repo。

發布後維護者應啟用 GitHub Private vulnerability reporting。未啟用前，請先用不含利用細節的 issue 請維護者提供私下回報方式；勿公開客戶檔、憑證或敏感利用資料。
