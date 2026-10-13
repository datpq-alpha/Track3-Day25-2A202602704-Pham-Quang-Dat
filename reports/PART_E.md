# Bước 8 — Part E: Burn-rate alerting và error budget

`WindowSums` tạo prefix sum một lần, truy vấn mỗi cửa sổ O(1). `BurnRateAlerter` chỉ kích hoạt khi cả cửa sổ dài và ngắn đạt ngưỡng; gom các phút liên tiếp thành một episode và đóng episode ở cuối dữ liệu nếu vẫn đang firing. Các trường hợp biên gồm không có traffic, ngưỡng vừa bằng 14,4×, budget vừa hết và dữ liệu hai series lệch chiều dài đều được kiểm tra.

| Rule | Cửa sổ dài/ngắn | Burn rate | Hành động |
|---|---|---:|---|
| Fast burn | 1h / 5m | 14,4× | page |
| Slow burn | 6h / 30m | 6× | page |
| Budget leak | 3d / 6h | 1× | ticket |

## Kết quả public: 43.200 phút, SLO 99,5%

| Sự cố | Naive | Burn-rate | Delay burn-rate (phút) |
|---|---|---|---:|
| checkout_bug | page sau 1 phút | page | 27 |
| provider_outage | page ngay | page | 4 |
| deploy_blip | page sai | không page | — |
| slow_leak | bỏ sót ticket | ticket, không page | 1337 |
| degraded_evening | page sau 214 phút | page | 291 |
| night_spike | page sai | không page | — |
| small_bump | page sai | không page | — |

Naive có 7 page, 0 ticket, 3 false page; burn-rate có 3 page, 1 ticket, 0 false page và PASS mọi check. Độ trễ dài hơn ở sự cố nhẹ là có chủ đích: cửa sổ dài xác nhận mức tiêu budget đáng kể, cửa sổ ngắn xác nhận lỗi vẫn tiếp diễn.

Tổng request **25.901.755**, bad **55.618**, allowed bad **129.508,8**, availability **99,7853%**. Budget consumed **42,95%**, remaining **57,05%**, `freeze_releases = false`. Quyết định freeze dùng budget thực trước làm tròn để không freeze sớm khi còn một lượng nhỏ budget.

`small_bump` có 1.794 bad request, khoảng 1,385% budget tháng. Burn 1h cao nhất trong sự cố và 60 phút sau là 8,225× (<14,4×), burn 6h cao nhất 1,911× (<6×). Vì vậy không page, dù tỷ lệ lỗi trong 5 phút có thể vượt ngưỡng cố định 5% của naive.

Kết quả thường: `reports/slo.json`. Mốc giữ riêng: `reports/part_e_runs/run_001/`, gồm score/event/budget đầy đủ, rules, source snapshot và checksum dữ liệu đầu vào. Bảy test gốc + bảy test biên đều pass; Ruff pass. Chưa có dữ liệu SLO ẩn của giảng viên.

```powershell
python -m pytest tests/test_alerting.py tests/test_alerting_boundaries.py -q -p no:cacheprovider
python scripts/run_slo.py --alerter both
```
