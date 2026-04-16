# 狀態標記的可靠性

[Situation] cron 狀態標記為 error 但功能正常執行
[Wrong] 僅依賴狀態標記判斷任務成功
[Correct] 驗證實際執行結果，不要只看狀態
[Behavior Change] 未來對關鍵任務進行雙重驗證
[Activation] 當需要判斷定時任務是否成功時

[Metadata]: {"source": "2026-03-23", "author": "Eve", "expected_impact": "提高任務監控準確性", "timestamp": "2026-03-29T13:30:00Z"}
