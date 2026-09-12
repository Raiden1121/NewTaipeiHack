# ROC 103 歷史人口分母設計

## 目標

補上青年參政 analytics 在 ROC 103（2014）所需的新北市 18–35 歲人口分母，讓 103 年每十萬參選率與 YRR 能使用同年度、同地理範圍的人口資料計算。

## 已確認的官方來源

- 來源資料集：內政部戶政司「各村（里）戶籍人口統計月報表」歷史資源。
- 來源 partition：`10312`（2014 年 12 月）。
- 檔案：`opendata-10312_age-65000.csv`，新北市 1,032 個村里，含單一年齡男女欄位。
- 交叉核對：新北市 29 區總人口加總為 `3,966,818`，與新北市 103 年人口統計年報一致。
- 103 年民政局 ODS 只提供五歲年齡組，不能直接精確加總 18–35；它作為交叉核對資料，不作本功能的主輸入。

## 架構與資料流

```text
官方 data.gov ZIP
  -> historical_population collector
  -> 既有 population canonical raw 欄位
  -> 既有 transform_population
  -> data/curated/population/10312.json
  -> authoritative dataset index
  -> youth_participation analytics
```

- collector 只負責下載、驗證 ZIP/CSV、保留來源 artifact，並把來源欄位轉成既有 `population` raw contract。
- transform 與 analytics 不分辨 ODRP014 或歷史 archive；兩者繼續使用既有 `population` dataset 與 18–35 歲公式。
- `10312` 是明確的歷史必要 partition，不把 2014 人口套用到其他月份，也不以估算補出缺少的月份。
- `population_villages` 維持目前 ODRP014 流程；它是服務涵蓋率輸入，不是青年參政分母。

## Canonical raw contract

每個來源村里列轉成既有欄位：

- `statistic_yyymm`, `site_id`, `village`, `people_total`；
- `people_age_{age:03d}_m/f`，至少完整保存 18–35 歲；
- `source_dataset`, `source_file`, `source_row` 保存歷史來源識別資訊；完整 CSV 另以 ZIP artifact 保存。

`transform_population` 仍以 `site_id` 對應 29 區，產生 `people_total`、男女及總和四種 district metrics。

## 保留策略

rolling retention 對月 partition 仍維持預設五年，但允許傳入 dataset-specific protected partitions。選舉 analytics 所需的年末人口 anchors `population: {"10312", "10712", "11112"}` 會同時保護 raw、curated、quality、quarantine 與 dataset index entry，避免下一次 refresh 把 2014、2018 或 2022 分母刪掉。只有 10312 使用本設計新增的歷史 archive；10712 與 11112 仍使用 ODRP014。

## 不在本次範圍

- 不以五歲組人口估算單歲人口。
- 不補齊 ROC 103 每個月份。
- 不改變 107–115 現有 ODRP014 輸出。
- 不把 10312 歷史人口套用到 `population_villages` 或其他 analytics。
