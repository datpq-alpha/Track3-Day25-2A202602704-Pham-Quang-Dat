# Part C — ResilientClient

## Cách hoạt động

- `ladder()` giữ thứ tự fallback nhưng loại model không hỗ trợ tool khi task là `tool`.
- `start()` nạp retry budget một lần cho mỗi logical call và khởi tạo trạng thái định tuyến.
- `_route()` bỏ qua provider đang cooldown hoặc bị breaker chặn; failover gửi ngay, không mang theo backoff của provider cũ.
- `_try_send()` giới hạn số attempt theo từng provider trong một logical call. Lần quay lại provider sau cooldown vẫn được đếm và phải tiêu retry token. Provider mới không tiêu retry token.
- `on_success()` gửi kết quả và latency cho breaker để phát hiện cả phản hồi thành công nhưng chậm.
- `on_cancel()` trả permit để không chiếm mãi slot HALF_OPEN khi request bị hủy.

| Loại lỗi | Breaker | Quyết định |
|---|---|---|
| Request sai, như 400 | Trả permit, không ghi lỗi | Dừng ngay, không retry/failover |
| 429 hết quota | Trả permit | Cooldown dài rồi chuyển provider |
| 429 rate limit | Trả permit | Cooldown ít nhất `retry_after`, chuyển provider ngay |
| Quá tải, lỗi server, timeout | Ghi nhận lỗi | Retry cùng provider nếu breaker cho phép, còn attempt, budget và deadline; nếu không thì chuyển provider |

Cooldown dùng chung giữa các call và không bị rút ngắn bởi kết quả đến sau. Khi không còn provider dùng ngay được, chỉ chờ cooldown rate limit tối đa 5 giây nếu còn đủ deadline. Không chờ cooldown quota, kể cả lúc nó sắp hết hạn.

## Cấu hình

Chỉ chỉnh `client.attempt_timeout_s` từ 8 xuống 6 giây. Trên seed 25, G2 p95 giảm từ 10,362 xuống 8,896 giây, availability vẫn 100%; amplification tăng từ 1,037 lên 1,046. Đây là đánh đổi giữa chuyển provider sớm hơn và số attempt bổ sung. Timeout 6 giây vẫn cao hơn ngưỡng slow call 5 giây để breaker có thể nhận diện phản hồi thành công nhưng chậm.

Các tham số chính còn lại giữ nguyên sau kiểm chứng:

- `max_attempts_per_provider: 2`: tối đa một retry trên mỗi provider cho một logical call.
- `retry_budget_ratio: 0.1`, `min_per_s: 0.5`, `max_tokens: 20`: G3 retry ratio là 0,049, dưới ngưỡng 0,10. Đây không phải giới hạn cứng 10% vì còn token ban đầu và refill theo thời gian.
- Backoff base 0,25 giây, cap 4 giây: retry có jitter, không làm chậm failover.
- Breaker window 20, min calls 10, failure threshold 0,5; slow call 5 giây, slow threshold 0,6: G4 p95 là 5,604 giây, dưới ngưỡng 10 giây.
- Open duration 10 giây, tối đa 2 probe, cần 2 probe thành công: sau phục hồi, primary share ở G2/G4/G6 đạt 100% trên seed 25.
- Quota cooldown 300 giây: tránh gọi lại tài khoản hết quota; G5 đạt availability 81,79%, không retry lỗi request và không failover vô ích trong cửa sổ bad deploy.
- `min_time_left_s: 1.0`: không gửi attempt khi còn quá ít thời gian; timeout từng attempt luôn bị giới hạn bởi deadline của call.

## Kết quả seed 25

| Kịch bản | Availability naive | Availability resilient | p95 resilient (s) | Attempt/call resilient | Kết quả |
|---|---:|---:|---:|---:|---|
| G1 | 71,94% | 100% | 4,738 | 1,063 | PASS |
| G2 | 45,60% | 100% | 8,896 | 1,046 | PASS |
| G3 | 100% | 100% | 4,569 | 1,083 | PASS |
| G4 | 100% | 100% | 5,604 | 1,029 | PASS |
| G5 | 36,99% | 81,79% | 5,477 | 1,003 | PASS |
| G6 | 51,70% | 99,96% | 5,982 | 1,058 | PASS |

G2 naive cần 155 giây để hồi phục, resilient đạt `recovery_s = 0` theo phép đo cửa sổ của simulator. Con số này phản ánh tỷ lệ call thành công nhờ fallback, không có nghĩa breaker lập tức đóng tại thời điểm provider hồi phục.

## Kiểm chứng

- 60 test pass: A, B, C, 9 test định tuyến bổ sung và test sanity của simulator.
- Ruff pass cho client và test bổ sung; `git diff --check` pass.
- 6/6 kịch bản public PASS trên từng seed 25, 26, 27: tổng cộng 18/18 lượt kiểm chứng. Chưa kiểm chứng băng ẩn của giảng viên.
- Số liệu và CSV: `reports/gameday/naive.json`, `resilient.json`, `resilient_multiseed.json` và các file timeseries. Thư mục này được `.gitignore` bỏ qua theo cấu hình sẵn của repo.

Chạy lại trên PowerShell sau khi kích hoạt môi trường ảo:

```powershell
python -m pytest tests/test_errors_retry.py tests/test_breaker.py tests/test_client.py tests/test_client_routing.py tests/test_sim_sanity.py -q -p no:cacheprovider
python scripts/run_gameday.py --client both
python scripts/run_gameday.py --client resilient --seed 26 --out reports/gameday/seed26
python scripts/run_gameday.py --client resilient --seed 27 --out reports/gameday/seed27
```
