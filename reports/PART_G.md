# Bước 6 — Part G: Semantic cache và stale-if-error

Kết quả chốt: cache threshold **0,90**, TTL **30 giây**, stale window **300 giây**, tối đa **500 entry**. C1 PASS trên seed 25, 26, 27; 83 test liên quan đều pass. Chưa chạy băng ẩn của giảng viên.

## Những phần đã làm

Trong `src/gameday_lab/cache.py`:

- `SemanticCache.lookup()` chọn entry có cosine similarity cao nhất, đạt ngưỡng và cùng `prompt_version`. Câu hỏi cá nhân luôn cache miss. Entry vượt quá `ttl_s + max_stale_s` bị xóa; lookup chỉ cập nhật LRU, không gia hạn TTL.
- `store()` không lưu câu hỏi cá nhân hoặc answer khác prompt version với request. Câu tương tự trong cùng scope được thay bằng answer mới thay vì tạo thêm bản trùng. Khi vượt dung lượng, xóa entry ít được dùng gần đây nhất.
- `invalidate(source)` xóa mọi answer dùng tài liệu đó, kể cả entry stale và entry thuộc prompt version khác.
- `CachingClient.start()` trả `Serve` ngay nếu có hit còn tươi; không gọi provider và không nạp token vào retry budget cho một cache hit.
- Cache miss hoặc hit stale vẫn đi qua `ResilientClient`. `on_success()` báo kết quả cho client bên trong trước rồi mới lưu answer, để breaker không mất tín hiệu sức khỏe provider.
- Khi client bên trong trả `GiveUp`, `_or_stale()` lookup lại tại thời điểm đó và chỉ dùng entry vẫn hợp lệ. Việc lookup lại tránh dùng answer đã bị webhook vô hiệu hóa hoặc đã hết hạn trong lúc provider đang xử lý.
- `on_content_update()` invalidate theo source và chuyển tiếp webhook; callback hủy request tiếp tục được chuyển cho inner client để trả slot probe.

Không sửa simulator, kịch bản hay test có sẵn. Thêm 6 test trong `tests/test_cache_safety.py` cho invalidation trong lúc request đang chạy, entry hết hạn giữa chừng, refresh đồng thời, TTL không bị kéo dài bởi hit, prompt scope và invalidation nhiều scope.

## Đối chứng seed 25

| Client / cấu hình | Availability | FAQ availability | Cache hit | Stale served | Wrong | Outdated | Cost/good turn | PASS |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Resilient, không cache | 83,73% | 84,24% | 0% | 0 | 0 | 0 | 1,386 | Không |
| Cache starter: 0,80 / 600 / 0 | 84,69% | 85,87% | 74,2% | 0 | 181 | 80 | 0,921 | Không |
| Cache chốt: 0,90 / 30 / 300 | 91,24% | 96,45% | 59,2% | 192 | 0 | 2 | 0,955 | Có |

FAQ availability tăng **12,21 điểm phần trăm** so với không cache; cost/good turn giảm khoảng **31,1%**. Cost là đơn vị chi phí tương đối của simulator, không phải tiền thật. Hit cao của starter không đủ để kết luận cache tốt: nó trả nhầm câu hỏi và giữ tài liệu lỗi thời.

Đối chứng không cache FAIL tiêu chí C1 là kết quả mong đợi: khi mọi provider sập, không có cached response để cứu FAQ.

## Ba thí nghiệm cho mục 8 của báo cáo

Các bảng dưới dùng seed 25. Mỗi thí nghiệm chỉ đổi một tham số so với cấu hình chốt; số liệu đầy đủ của cả 3 seed nằm trong `part_g_runs/run_001/summary.csv`.

### 1. Ngưỡng tương đồng

| Threshold | FAQ availability | Hit ratio | Wrong | Lý do wrong | Cost/good turn |
|---|---:|---:|---:|---|---:|
| 0,80 | 85,93% | 61,0% | 181 | `other_question` | 1,016 |
| 0,90 | 96,45% | 59,2% | 0 | Không | 0,955 |
| 0,97 | 96,40% | 49,9% | 0 | Không | 1,018 |

Ngưỡng 0,80 nhận cả câu gần về nghĩa nhưng khác yêu cầu. Catalog có các cặp như chính sách hoàn tiền/thời gian hoàn tiền, đổi size/đổi màu, phí ship nội thành/ngoại tỉnh; tổng metric `other_question` không xác định riêng số lần của từng cặp. Không suy ra cặp nào cụ thể chỉ từ con số 181.

Ngưỡng 0,97 loại nhiều cách diễn đạt lại của cùng một ý; seed 25 không đạt tiêu chí hit ratio tối thiểu 50%. Chọn 0,90 vì không có wrong answer trên cả 3 seed, trong khi hit ratio giữ ở 59,1–59,2%.

### 2. TTL

| TTL (s) | FAQ availability | Hit ratio | Outdated | Cost/good turn |
|---|---:|---:|---:|---:|
| 30 | 96,45% | 59,2% | 2 | 0,955 |
| 60 | 96,45% | 65,2% | 3 | 0,915 |
| 300 | 96,40% | 73,1% | 95 | 0,863 |

TTL 60 cũng PASS trên 3 seed và tiết kiệm chi phí hơn. Chọn TTL 30 để giới hạn tuổi answer được dùng trực tiếp xuống 30 giây khi nguồn đổi không báo trước, đổi lại hit ratio thấp hơn nhưng vẫn vượt 50%. Đây là lựa chọn về độ tươi, không phải khẳng định TTL 30 luôn có ít outdated answer hơn TTL 60 trên mọi seed.

TTL 300 giữ answer cũ quá lâu: outdated lần lượt là 95/96/100 trên seed 25/26/27, vượt giới hạn 15. Webhook không giúp với thay đổi im lặng vì không có sự kiện để gọi invalidate; TTL buộc lần đọc sau hạn phải hỏi provider lại. Số outdated không nhất thiết tăng đều theo TTL trên từng seed vì thời điểm refresh cũng thay đổi.

### 3. Stale-if-error

| Max stale (s) | FAQ availability | Hit ratio | Stale served | Wrong | Cost/good turn |
|---|---:|---:|---:|---:|---:|
| 0 | 85,29% | 48,1% | 0 | 0 | 1,033 |
| 300 | 96,45% | 59,2% | 192 | 0 | 0,955 |

Tắt stale-if-error làm FAQ availability giảm **11,16 điểm phần trăm**, vì cache hết TTL trong lúc provider đang sập. Stale window 300 giây đủ bao phủ outage 120 giây và có dư địa; stale chỉ được dùng sau khi provider không trả lời được, không thay thế refresh khi provider khỏe.

Webhook và prompt scope vẫn được kiểm tra trước khi serve stale. Lookup không kéo dài tuổi entry: tuổi tối đa là 30 + 300 = 330 giây kể từ lúc lưu.

## Kiểm chứng nhiều seed

| Seed | FAQ availability | Cache hit | Wrong | Outdated | Stale served | PASS |
|---|---:|---:|---:|---:|---:|---|
| 25 | 96,45% | 59,2% | 0 | 2 | 192 | Có |
| 26 | 95,40% | 59,1% | 0 | 4 | 224 | Có |
| 27 | 96,27% | 59,1% | 0 | 7 | 225 | Có |

Các điều kiện C1: wrong = 0, outdated ≤ 15, FAQ availability ≥ 93%, hit ratio ≥ 50% đều đạt. Không có lỗi `other_user`, `personal_cached`, `old_prompt` hoặc `ignored_invalidation`.

## Các câu hỏi cho báo cáo

**Vì sao không cache câu hỏi cá nhân, kể cả cache theo user?** Trạng thái đơn hàng, tiền hoàn và điểm tích lũy thay đổi theo thời gian. Tách user chỉ tránh trả dữ liệu của người khác, không đảm bảo dữ liệu của chính user còn đúng. Lab loại toàn bộ nhóm personal khỏi allowlist; nếu muốn cache nhóm này trong sản phẩm thật cần cơ chế nhất quán và invalidation phù hợp từng loại dữ liệu.

**Dashboard vẫn xanh nhờ cache thì alert bằng gì?** Theo dõi lỗi/timeout của các attempt gọi provider, trạng thái và lịch sử mở breaker, tỷ lệ stale served và tuổi stale answer; tách những số này khỏi availability của câu trả lời cuối cùng. Báo động dựa chỉ vào thành công cuối cùng có thể bỏ sót outage đã được cache che đi.

**Giới hạn còn lại:** nếu nguồn đổi im lặng đúng lúc provider sập, stale answer có thể lỗi thời đến hết cửa sổ stale. Webhook vẫn invalidate ngay nếu được gửi; ngưỡng similarity và TTL không tự xác minh nội dung nguồn. Đây là đánh đổi cần giải thích khi đưa stale-if-error vào production.

## Kết quả đã lưu để đối chiếu lượt sau

Đợt đã chốt: **`reports/part_g_runs/run_001/`**. Thư mục này không nằm trong các đường dẫn kết quả bị `.gitignore` bỏ qua của starter.

- `summary.csv` / `summary.json`: 24 lượt chạy = 8 cấu hình khác nhau × 3 seed. `ttl_030` dùng lại kết quả `chosen`, được ghi rõ bằng alias trong manifest.
- `manifest.json`: tham số từng thí nghiệm, seed simulator, seed client, phiên bản Python và SHA-256 các file nguồn/đầu vào.
- `input_config.yaml` / `reference_config.yaml`: cấu hình starter trước khi tinh chỉnh cache.
- `selected_config.yaml`: cấu hình đầy đủ sau khi chốt, gồm cả client của Part C.
- `source/`: bản sao mã nguồn đã chạy, gồm simulator, client, cache và script thí nghiệm.
- Mỗi thư mục cấu hình có `settings.json`; mỗi seed có metric/check đầy đủ và CSV timeseries riêng.
- `FINAL.json`: cấu hình được chọn, kết quả kiểm chứng và checksum các file chốt.

Kết quả chạy lệnh chuẩn còn nằm trong `reports/cache/` để tiện xem; đây là thư mục kết quả có thể bị ghi đè khi chạy lại. Dùng `part_g_runs/run_001/` làm mốc cố định cho báo cáo, không lấy số từ nhiều cấu hình/seed khác nhau ghép thành một hàng.

`scripts/run_cache_experiments.py` tự tạo `run_002`, `run_003`, … cho lượt mới; nếu truyền `--out` trùng thư mục đã tồn tại thì từ chối ghi đè. Lượt sau dùng cùng seed để so sánh công bằng; đối chiếu thêm `source_sha256` nếu có sửa thuật toán.

Chạy từ thư mục gốc repo sau khi kích hoạt `.venv`:

```powershell
# Kiểm tra phần G và các phần A–C liên quan
python -m pytest tests/test_errors_retry.py tests/test_breaker.py tests/test_client.py tests/test_client_routing.py tests/test_cache.py tests/test_cache_safety.py tests/test_sim_sanity.py -q -p no:cacheprovider

# Tương đương make cache; có ghi đè kết quả thường trong reports/cache
python scripts/run_gameday.py --scenarios configs/scenarios_cache.yaml --client resilient,cached --out reports/cache

# Tạo đợt thí nghiệm mới, đối chứng với cấu hình starter đã giữ lại
python scripts/run_cache_experiments.py --reference-config reports/part_g_runs/run_001/input_config.yaml

# Có thể thử tham số khác; kết quả tiếp tục được lưu ở thư mục mới
python scripts/run_cache_experiments.py --reference-config reports/part_g_runs/run_001/input_config.yaml --ttl-s 60
```

Muốn tái chạy đúng mã nguồn cũ sau khi repo đã thay đổi, dùng runner trong bản sao `source/` và cấu hình đã chốt, đồng thời chỉ định một thư mục kết quả mới:

```powershell
python reports/part_g_runs/run_001/source/scripts/run_cache_experiments.py --config reports/part_g_runs/run_001/selected_config.yaml --reference-config reports/part_g_runs/run_001/input_config.yaml --scenarios reports/part_g_runs/run_001/scenarios_cache.yaml --out reports/part_g_runs/replay_run_001
```
