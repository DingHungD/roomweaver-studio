# 全圖、原像素切片與 Agent 複核

所有者：跨案件共用的 Roomweaver 核心。實作在 `src/interior/object_recognition/`；案件輸出必須選新的本案 run。原圖、原CAD、既有判讀與標註均不覆寫。

## 輸入與自動執行

新CAD平面首次判讀預設勾選物件模型，先YOLO再Agent；已有判讀的專案重開維持原不勾選預設，圖片入口維持原預設，亦可手動取消。既有用途判讀、Q/M、來源／尺度保護、採用、3D、編輯與輸出接續原流程。本機已明確配置模型時即可使用，沒有設定仍顯示原設定問題，不偷偷下載或改供應商。

[通用外框判讀規則](OBJECT_RECOGNITION_RULES.md)由`native_policy`隨程式載入，版本納入快取綁定。`native-policy.json`記錄首末點完全相同的衍生closed正規化，原始點與來源不改。新增`mask_spec.method="hull"`由refs全部原生點推導凸包，只允許furniture／chair／sofa，禁止用於牆門窗；來源不明、改類或不充分刪除證據仍保留待辦。帶有`human_confirmation`的物件禁止自動改類／丟棄，保留人類語意備註。提示只載入通用技巧，不讀私有開發案例物件座標、參考mask或修正清單當新案答案。



Agent只需提供整張原圖、指定的 segmentation 權重及新輸出目錄：

```powershell
python -m interior.object_recognition --image <整張原圖.png> --checkpoint <已訓練的模型.pt> --output <本案新run>
```

模型為本機選用依賴，安裝 `.[recognition]`；CUDA版PyTorch另依本機GPU安裝。Studio可以使用另一個Python環境執行YOLO，主應用不用載入PyTorch。此功能不自動下載模型或啟用雲端服務。

預設先推論完整圖（`imgsz=1536`，這條分支會等比例縮放），再執行兩個尺度：原像素640×640切片、原圖縮小一半後640×640切片。兩者X/Y步距均為480、重疊25%，小圖模型輸入均為640。原像素分支不縮放；半尺寸分支約涵蓋原圖1280×1280區域，提供長牆等完整視野。邊緣不足640只在右／下補白。可用`pyramid_scales:[1.0]`重播單尺度，預設`[1.0,0.5]`。

每個view同時記錄縮小圖的scaled_box／scaled_size、實際X/Y比例及原圖box；奇數高度依實際比例還原，不能只把座標乘2。二進位mask使用全域格點最近鄰還原至原圖，輪廓／孔洞依還原後mask重新取得。

預設legacy政策：各尺度結果還原後依同類別二進位mask IoU≥0.50去重。保留全圖完整mask為代表，避免高分局部片段取代長牆；若截斷片段有≥90%像素被另一視圖的完整同類物件包含，記為該物件的contained_fragments，不額外畫成新物件，也不算作優先候選的完整輪廓支持。保留raw追溯，不以mask聯集捏造新輪廓。不同類別的重疊不互相壓掉，交給Agent核對。碎片不能只因同類相鄰就合成一件。

### 結構物件合併政策structural_v2

選用options `{"merge_policy":"structural_v2"}`，其他依賴及切片方式相同。跨案件核心`structural_merge`只讀模型預測，沒有CAD／人工標註輸入。先沿用legacy候選，再對wall／beam／track_light分組。牆以實際交集／較小遮罩面積≥0.60，樑另核對方向；細軌道燈以長軸重疊≥0.60、相同方向與法向偏移判斷粗細不同的重複，不將平行／垂直不同燈合併。

有完整全圖牆代表的群組中，後續片段必須直接符合其中一個全圖代表；不能透過短片段串接另一完整牆。強重疊全圖牆可保留彼此已有分支，其他新增像素要有至少兩個不同視圖支持；細線按實際長軸覆蓋範圍投票。只保留接到代表的來源預測像素，不填任意大框、補空隙或把整張同類圖層聯集。每件保存成員／視圖、anchor_raw_id及增減像素；改過輪廓不列優先已正確物件，一律Agent複核、accepted=False。窗與其他非目標類別保持原mask。


共用核心及v1／v2案件啟動器仍預設legacy；不同merge_policy的快取不得混用。沒有修改全域Studio設定或部署模型。`tests/test_structural_merge.py`以合成資料覆蓋同視圖重複、跨尺度細線、平行／垂直獨立物件、窗牆分開、雙視圖接縫延伸、單視圖不補、孔洞與輸入不變、片段不能串接兩完整牆等失敗情況。

輸出：`tiles/`（實際640模型輸入）、`views.json`（來源框與偏移）、`raw.json`及無損二進位mask、`candidates.json`及mask、依類別分組的`layers.json`、合併大圖`candidates.png`、切片格線`tile-layout.png`及逐件局部圖。所有輸出起始皆未確認，accepted=0。來源及權重SHA256綁定在`config.json`，失敗寫`status.json`，禁止覆寫既有run。

## Agent：看候選、套圖層、再查漏

### Studio核對平面整合

在「判讀圖面／重新判讀」勾選「使用物件模型協助核對」，再按原有Agent判讀按鈕；新CAD首次判讀預設勾選，其餘入口沿用原預設，取消勾選不會調用模型。沿用使用者選定的Agent模型。流程為prepare → studio_pipeline → run_semantics：整圖YOLO、640原尺寸／半尺寸、25%重疊及structural_v2去重，然後逐件核對全部候選與原生CAD文字／附近物件，最多兩輪來源修正、套層及六區查漏。完成的物件與待辦會交給後續用途、牆門窗、家具、lighting及drawing_objects判讀；不依賴事先知道的FP清單或案件腳本。

conservative_review保留有爭議的原候選：改類、大幅輪廓差異、沒有充分同類重疊證據的移除均列待辦。細玻璃／燈具可在原mask內縮至真實來源投影，不用此例外截短一般牆。原生建議與保留版本並存，defer不會消失；保守合併後再次看實際圖層，回查無發現也不能清空待辦。本案已確認答覆作為語意證據並納入快取來源綁定。

結果區新增「物件辨識與圖層回查」，可切換「綜合物件結果」及「用途、牆門窗與配置」，沿用分類與點選。輪廓依局部CAD公尺座標顯示多輪廓／孔洞，不以外接矩形代替。待辦或查漏存在時阻擋採用，重新開啟及採用前的重新驗證也保留門檻。複雜投影留在綜合物件圖層，不強制轉成錯誤的簡化3D占位。

本機一次設定（不下載權重或Python、不修改案件）：

```powershell
python tools/configure_object_recognition.py --workspace <既有應用workspace> --python <YOLO環境python.exe> --checkpoint <已訓練segmentation.pt> --enable
```

設定存應用workspace的object-recognition.json，舊檔先備份。新增workflow:"agent_native_v1"與options.merge_policy:"structural_v2"；推論另存checkpoint自己的taxonomy.json，不讀案件標註表。checkpoint SHA256在快取重用時也核對。主應用需numpy／Pillow／shapely，YOLO使用指定的獨立Python，不要求主環境安裝torch。ROOMWEAVER_YOLO_CONFIG仍優先。未設定卻勾選時明確提示設定問題，不偷偷下載或換模型。API的use_object_recognition=false明確略過，舊API省略時沿用原設定。

每個新工作保存yolo-inference／yolo-native-review：類別表、候選、Agent請求／回覆、原生建議、admission.json、實際綜合objects.json／mask、object-layers.json／SVG、回查與frozen-result.json。來源、模型、候選、類別、已確認答覆及保守政策綁定；部分失敗保留證據，需新工作。原件、既有判讀及採用狀態保持。

實測限制：指定11筆FP的先前修正可達同圖100%／100%，不能套作全面自動成績。本次不給FP編號／參考mask的真實全候選Agent測試，全面重畫曾降為81.7%／81.7%；通用保守合併後為precision92.2%／recall100%，嚴格IoU≥0.90達55／71，但仍17筆爭議建議及5項套層問題，狀態blocked。沒有宣稱新圖99%。評估只在輸出凍結後另讀參考，正式無參考工作precision／recall維持null。完整開發證據在本機artifacts/verification/studio-yolo-pipeline-20261024。

Studio的`run_semantics`已接入選用流程：本機YOLO推論 → Agent看原圖／合併候選、CAD幾何與原生文字 → 原有來源綁定及局部補判 → 逐件遮罩複核 → 保存已複核YOLO圖層與來源判讀圖層 → 分區回查套層後全圖，列出遺漏與衝突。使用既有Agent選取模型，不切換供應商。

啟用時在應用workspace放`object-recognition.json`，或以`ROOMWEAVER_YOLO_CONFIG`指定本機設定；沒有設定時沿用既有Agent流程。機器專用Python路徑留在應用workspace，不能寫進可攜案件設定：

```json
{
  "enabled": true,
  "python": "<本機YOLO環境的python完整路徑>",
  "checkpoint": "<指定權重完整路徑>",
  "checkpoint_sha256": "<實際SHA256>",
  "options": {"imgsz": 1536, "tile_size": 640, "overlap": 0.25, "pyramid_scales": [1.0, 0.5]}
}
```

文字鄰近查詢只提供證據，不能直接決定關聯。Agent需綜合引線、方向、周邊構件與用途；純需求文字不建立定位物件。每件候選必須accept/reject/defer；accept需要類別及整件mask都正確，並引用附近真實CAD幾何。格式錯誤、未知來源、只引文字或不完整mask都不能進已複核圖層。Agent修正或補出的物件沿原有來源綁定規則記錄，不算YOLO原始正確。

`yolo-review/`保存每批請求／回覆、逐項決定、已複核mask、Agent判讀的語意圖層與套層預覽、逐區遺漏檢查。未處理候選、掃描失敗或發現遺漏會使本次報告blocked，保留工具待辦，不轉成使用者Q。這仍是預覽，不改原DWG圖層、不自動採用設計。

## Precision目標與限制

### 限定目標Agent複核（2026-10-24）

`focused_review.run`接受明確目標ID與來源視窗，初始保留全部模型候選，只處理targets；nearby_objects及原生CAD文字／幾何供關聯判斷，不把最近文字當答案。每個decision含真實來源，duplicate_of指向保留代表；不能刪除／改動非目標。defer保留原預測並列待辦，不能藉刪除不確定項美化precision。keep保留目前已修正的mask與mask_spec，不退回初始YOLO。additions及replace只由原生來源建形，無自由座標。

修正後保存分類JSON、可編輯分類SVG及mask疊圖，真實Agent看全圖與六區；有問題時只作有界目標修正，非目標發現保留紀錄。完成後以freeze_review鎖定輸出，另由compare_review評估。新版類別可傳`classes_path`，透過training_class_id明確映射，不能用canonical ID直接誤評模型ID。

家具／設備／窗的封閉外框可包含框內空白；開啟的玻璃門／隔屏需按各封閉實體投影聯集，開門弧僅作參照，不能把隔屏與斜向門扇之間空白一律填為玻璃。此區分必須與既定類別語意一致，不能只為提高IoU選包絡。


`tests/test_focused_segmentation_review.py`合成檢查defer不消失、非目標逐像素保留、keep不藏邊界修改、原生修正keep不退回、重複引用／來源驗證及凍結評估的訓練ID映射。真實Agent回覆／套層檢查與單元測試分開保存，不以替身測試代表實際辨識。

### 來源限定的真實Agent分割複核（2026-10-24）

共用`agent_review.run`接受本案原生site、原圖、既有YOLO bundle、類別ID／名稱及runtime；分6區逐件keep/replace/reject/defer，再分6區查漏，保存分類圖層及全圖／局部回查。CAD文字保留ID／位置，附近幾何與物件只作證據，不以最近文字直接定類；提示內的圖面文字視為資料。

新mask只允許由實際封閉來源、來源包絡、指定邊線／平行雙邊或可追溯細線推導，不能自由填座標、純文字新增或把需求敘述當定位物件。`agent_finish.finish`依套層發現作有界修正；`source_bind_review.bind_and_verify`只對Agent明確點名、已有唯一封閉來源的物件實作來源重繪，再真實看圖核對；來源不明必須停止該修正。保存中間版本，最後待判依ID去重，歷史不刪。

`review_report.freeze_review`先鎖定結果JSON／mask／圖層／回查雜湊；獨立的`compare_review`核對後才讀參考，按相同類別／mask門檻計前後分數，不可依計分結果回填本輪答案。輸出可編輯分類SVG、圖層JSON與原像素mask，屬另外保存的預覽，未寫回原DWG或應用採用狀態。這個分割實驗入口不等同完整3D／設計採用驗收；既有Studio選用整合仍按上文設定啟用。

主Agent流程需既有agent選用依賴及numpy、Pillow、shapely；不載入torch。計分環境另需numpy／scipy／Pillow；可用既有YOLO環境。案件啟動器由使用者在本機配置，案件腳本只提供來源／輸出與runtime，核心不依賴案例。新執行目錄不可覆寫。


### 評估口徑

類別／實例規則改版時，使用`taxonomy_compare`對同一新版參考重新計算全部模型；不能直接比較不同標註版本的舊分數。`reference_for_training_ids`以明確training_class_id評分，保留canonical ID追溯；`migrate_predictions`僅以類別名稱合併既定方框家具，不改舊mask／信心值，舊的無對應類別仍計FP。所有模型映射後套相同mask合併與confidence門檻，不把舊牆段依答案聯集合成完整連通牆。


confidence≥0.85、有另一視圖confidence≥0.25且mask IoU≥0.80、非截斷且無強烈異類衝突，僅列優先複核，不能自動認定正確。其餘confidence≥0.25列一般候選，≥0.05原始候選另存診斷。

precision>99%是目標，不能用confidence=.99替代驗證，也不能把Agent補判算成YOLO精確率。應同時報告模型全部候選、選擇性候選的precision／recall，以及Agent的接受／退回數；沒有參考標註的判讀回合precision必須null。mask IoU≥0.50只是既有評估門檻，不等於完全正確的輪廓；需另看嚴格輪廓門檻與局部圖。

第一版只在一張圖的93件物件訓練；新增切片可能增加誤報，不能假定必然提升辨識。相同原始DWG的重播只能作開發比較，不能宣稱新圖泛化99%。評估工具`object_recognition.evaluation`在推論後另讀參考，推論模組不接收參考類別或mask。第二版的增強細節見[訓練增強](OBJECT_RECOGNITION_TRAINING.md)。

檢查：`tests/test_yolo_recognition.py`使用合成輸入核對固定步距、邊界補白、mask座標與孔洞、去重／完整全圖保留、未確認門檻、來源引用、Agent套層與回查；真實GPU推論及真實Agent驗證必須另外列出，不用替身測試冒充。
