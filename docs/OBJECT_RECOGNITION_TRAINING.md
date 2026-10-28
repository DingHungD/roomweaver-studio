# CAD segmentation訓練增強

所有者：跨案件共用訓練核心；案件輸入、來源分組及訓練次數由案件工作流指定。資料生成在`object_recognition.augmentation`，訓練在`object_recognition.training`，不反向讀取任何指定案件。需已有本機CUDA版PyTorch／recognition依賴；資料生成另使用主應用已有的Shapely。

## 第二版實驗設定

以已確認的分割多邊形生成三類視野：完整圖、原像素640切片、半尺寸640切片。每類產0／90／180／270度旋轉，影像與多邊形同步變換。裁切使用多邊形與視窗真實交集，不用整件外接框代替；不相連可見片段分行並追溯同一source_object_id。只有背景的切片保留負樣本。原類別ID不重排，原來源和品質旗標保持。

線上增強採：小角度旋轉±5度、平移±5%、縮放約0.75～1.25、水平／垂直翻轉各50%、Mosaic 35%、MixUp 5%、亮度小幅變化。Mosaic最後15輪關閉，讓模型回到單圖視野。沒有透視或剪切扭曲，以保留CAD幾何特徵；Copy-Paste／CutMix本輪關閉，避免在固定牆與家具間任意移植造成不合理場景。

另有10%批次的小範圍白色遮擋：同時清除該區影像和所有受影響instance mask，按可見mask重算box，完全被遮住或零面積目標移除。這不是只改圖片、不改標註的RandomErasing；Ultralytics的`erasing`參數屬分類增強，不能把設定值當成segmentation已生效。遮擋、修改及空目標刪除數會寫入augmentation audit。

細長軌道等圖樣使用本次進程專屬的box_candidates過濾門檻；不修改已安裝套件。mask_ratio=2、overlap_mask=false，以維持重疊物件獨立mask並控制GPU記憶體。模型preprocess移除真正空mask，不以虛構粗線增厚圖樣。遮罩／來源品質仍可能限制最細線條學習。

固定80輪、AdamW、初始lr=0.0003、cosine排程、warmup 3輪、batch=nbs=4，從指定第一版checkpoint微調。固定選最後80輪last.pt，不依測試結果挑epoch或最佳分數。保存設定、來源雜湊、環境、實際增強audit、loss及checkpoint。舊權重不覆寫，也不自動部署。

## 分組與評估

同一張原圖的旋轉、縮放、拼貼和切片都屬同一source_group，不可隨機拆成獨立訓練／驗證案件。訓練衍生圖只能用於擬合診斷，不能當作獨立驗證。

來自相同原始DWG的資料只可作同圖開發比較。應比較固定門檻下全圖、原像素組合、半尺寸及全部多尺度的precision／recall與嚴格mask IoU；優先候選的高precision需同時報告coverage，不能取代全部模型結果。Agent補判不計入模型原始成功。

增強不能憑空產生新建築樣式或增加真正獨立樣本。需要新案及按原始DWG分組的驗證集，才能判定泛化及precision>99%的目標。

參考：[Ultralytics增強說明](https://docs.ultralytics.com/guides/yolo-data-augmentation/)、[訓練設定](https://docs.ultralytics.com/modes/train/)。實際支援以本機8.4.184程式核對，不能直接套用分類任務的參數當分割增強。
