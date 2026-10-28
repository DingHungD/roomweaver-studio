# Third-party notices

`frontend/src/source-gallery/` 的 gallery、資源排程、沉浸導覽與樣式來自使用者提供的 `upstream-gallery-source`；原檔 SHA 見同目錄 `upstream.json`，本次修改含相對路徑、專案名稱及外部標籤跳脫。此處記錄來源，不將使用者提供內容另行宣稱為 MIT。Three.js 及其他套件保留原授權；案件圖片／製作母檔不納入共用程式碼授權。

`examples/from-3d/assets/` 包含 BlenderKit 免費 **CC0-1.0** 家具、材質與城市 HDRI，作者、來源、版本與 SHA-256 見該目錄 `manifest.json`。生成的 `.blend`／`.glb` 包含這些素材的衍生版本；其原始授權維持 CC0，原創程式與場景組合則採 MIT。沒有將 Royalty Free 素材納入公開資產包。完整來源見 [3D 範例](examples/from-3d/README.md)。

程式及原創合成範例採 MIT。第三方套件與外部程式保留各自授權，不因安裝本工具而改成 MIT。

前端 bundle 包含 React、React DOM、Scheduler、Three.js，MIT 授權文字保留於 [licenses/](licenses/)。其他建置與 Python 依賴授權隨套件安裝；版本見 npm lock、pyproject 及 requirements-lock。

Blender 和 Codex CLI 由使用者另行安裝，本 repo 不分發其 binary。匯入的模型、貼圖、材質參考仍屬原權利人，不因此變成可公開發布素材。

SKP 轉檔選用 [OpenSKP](https://github.com/iamahsanmehmood/openskp) 1.3.0（MIT），其依賴由 Python 套件安裝並保留各自授權。未使用或重分發 SketchUp C SDK、SketchUpAPI.dll 或 SketchUp 桌面軟體。OpenSKP 是第三方解析器，不隸屬 Trimble。
