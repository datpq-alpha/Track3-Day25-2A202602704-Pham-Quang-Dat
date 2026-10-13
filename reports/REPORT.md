# Lab 25B — Report

**Họ tên:** Phạm Quang Đạt  **MSSV:** 2A202602704

**Repo:** [Track3-Day25-2A202602704-Pham-Quang-Dat](https://github.com/datpq-alpha/Track3-Day25-2A202602704-Pham-Quang-Dat)

**Commit nộp bài:** `41eba05`  **Điểm tự động:** **84/88**. Còn 4 điểm SLO ẩn và 12 điểm báo cáo do giảng viên chấm.

Các bảng dùng simulator seed **25**, client seed **1**; kiểm chứng thêm trên seed **26, 27**. Các số thập phân giữ định dạng của JSON.

## 1. Kết quả Game Day: naive và resilient

| Băng | Client | Availability | p95 (s) | Amplification | Retry ratio | Cost/good turn | Recovery (s) | PASS |
|---|---|---:|---:|---:|---:|---:|---:|---|
| G1 | naive | 0.7194 | 7.157 | 7.738 | 6.738 | 2.163 | 4 | Không |
| G1 | resilient | 1.0000 | 4.738 | 1.063 | 0.002 | 2.106 | 0 | Có |
| G2 | naive | 0.4560 | 15.034 | 9.904 | 8.904 | 4.627 | 155 | Không |
| G2 | resilient | 1.0000 | 8.896 | 1.046 | 0.009 | 2.133 | 0 | Có |
| G3 | naive | 1.0000 | 4.768 | 1.164 | 0.164 | 2.328 | 0 | Không |
| G3 | resilient | 1.0000 | 4.569 | 1.083 | 0.049 | 2.177 | 0 | Có |
| G4 | naive | 1.0000 | 13.764 | 1.004 | 0.004 | 2.008 | 0 | Không |
| G4 | resilient | 1.0000 | 5.604 | 1.029 | 0.004 | 2.101 | 0 | Có |
| G5 | naive | 0.3699 | 5.359 | 17.030 | 16.030 | 2.124 | — | Không |
| G5 | resilient | 0.8179 | 5.477 | 1.003 | 0.003 | 2.504 | — | Có |
| G6 | naive | 0.5170 | 4.836 | 12.344 | 11.344 | 2.009 | 0 | Không |
| G6 | resilient | 0.9996 | 5.982 | 1.058 | 0.022 | 2.208 | 0 | Có |

Nguồn: `gameday/naive.json`, `gameday/resilient.json`. Resilient PASS 6/6 băng trên cả ba seed. Seed 25 không có retry-after violation, retry lỗi request, incompatible route hay unneeded failover; primary share sau phục hồi ở G2/G4/G6 là 1.000. G5 không có mốc restore nên recovery để —.

## 2. Cấu hình client và lý do

| Tham số | Giá trị | Lý do và bằng chứng |
|---|---:|---|
| attempt_timeout_s | 6 | G2 p95 giảm từ 10.362 (timeout 8) xuống 8.896; G6 availability 0.9996, cao hơn 0.9484 khi timeout 30 |
| max_attempts_per_provider | 2 | Tối đa một retry/provider; G2 amplification 1.046, G3 retry ratio 0.049 |
| min_time_left_s | 1 | Không cấp attempt khi còn quá ít deadline; G6 mặc định không có `deadline` give-up |
| backoff_base_s / cap_s | 0.25 / 4 | Full jitter cho retry cùng provider; G3 retry ratio 0.049 và amplification 1.083, failover không chờ backoff cũ |
| retry_budget_ratio | 0.1 | Khi breaker bị vô hiệu, G2 retry ratio 0.060 với budget so với 0.442 khi tắt budget |
| retry_budget_min_per_s / max_tokens | 0.5 / 20 | Cho một lượng retry khi ít traffic và burst nhỏ; ratio không phải giới hạn cứng 10% vì còn refill theo thời gian |
| quota_cooldown_s | 300 | G5 không retry 400, không failover vô ích trong bad deploy; availability đạt 0.8179 dù tài khoản A hết quota |
| breaker.window_size / min_calls | 20 / 10 | Bỏ kết quả cũ và cần đủ mẫu; G2 recovery 0 thay cho 155 của naive |
| breaker.failure_rate_threshold | 0.5 | Bắt lỗi provider; kết hợp budget giữ G3 retry ratio 0.049 ≤ 0.10 |
| breaker.slow_call_s / slow_rate_threshold | 5 / 0.6 | G4 có thể mở breaker vì chậm dù request thành công; p95 5.604 ≤ 10 |
| breaker.open_duration_s | 10 | Có khoảng nghỉ trước probe; G2/G4/G6 đạt primary share 1.000 sau phục hồi |
| breaker.half_open_max_probes / half_open_successes | 2 / 2 | Giới hạn request đang bay khi phục hồi; đủ hai probe nhanh mới đóng, test đồng thời và stale generation đều pass |

Đối chứng timeout 8 → 6 nằm trong `PART_C.md`; các thí nghiệm tiếp theo nằm ở mục 3.

| Loại lỗi | Ghi breaker? | Retry cùng provider? | Failover/cooldown |
|---|---|---|---|
| CLIENT_ERROR: 400/401/403… | Không, trả permit | Không | GiveUp ngay; malformed request không được cứu bằng đổi provider |
| QUOTA_EXHAUSTED | Không, trả permit | Không | Cooldown 300 giây; chuyển provider ngay |
| RATE_LIMITED | Không, trả permit | Chỉ nếu phải quay lại sau cooldown ngắn, còn budget/attempt/deadline | Cooldown dùng chung ít nhất `retry_after`; ưu tiên chuyển provider ngay |
| OVERLOADED / SERVER_ERROR / TIMEOUT | Có | Khi breaker cho phép, còn attempt, token và deadline; chờ full jitter | Nếu không retry được thì chuyển provider ngay |

Tool call chỉ đi provider hỗ trợ tool. Khi không còn provider dùng ngay được, chỉ chờ rate-limit cooldown tối đa 5 giây nếu còn deadline. Permit/generation giúp bỏ qua kết quả đến muộn sau lần chuyển trạng thái.

## 3. Ba thí nghiệm về client

Nguồn: `part_f_runs/run_001/summary.csv`, seed 25.

### 3.1. Retry budget là lớp phòng thủ cuối

Tất cả các hàng dưới đặt `max_attempts_per_provider = 5`. Nhánh breaker lỗi đặt `min_calls = 1000000000`; nhánh budget tắt đặt ratio 100, max tokens 1e9, refill 1e6/s.

| Breaker | Budget | Băng | Availability | Amplification | Retry ratio | Recovery (s) | p95 (s) |
|---|---|---|---:|---:|---:|---:|---:|
| Vô hiệu | Bật | G2 | 1.0000 | 1.400 | 0.060 | 0 | 15.621 |
| Vô hiệu | Tắt | G2 | 0.9729 | 1.672 | 0.442 | 42 | 18.527 |
| Vô hiệu | Bật | G3 | 1.0000 | 1.136 | 0.068 | 0 | 4.550 |
| Vô hiệu | Tắt | G3 | 1.0000 | 1.162 | 0.158 | 0 | 4.661 |
| Hoạt động | Bật | G2 | 1.0000 | 1.039 | 0.007 | 0 | 6.191 |
| Hoạt động | Tắt | G2 | 1.0000 | 1.039 | 0.007 | 0 | 6.191 |
| Hoạt động | Bật | G3 | 1.0000 | 1.034 | 0.020 | 0 | 4.754 |
| Hoạt động | Tắt | G3 | 1.0000 | 1.034 | 0.020 | 0 | 4.754 |

Khi breaker không mở, budget giảm retry ratio G2 từ 0.442 xuống 0.060 và recovery từ 42 xuống 0 giây; nhánh không budget có 64 GiveUp vì deadline. Khi breaker hoạt động đúng, bật/tắt budget cho cùng kết quả vì breaker đã chặn tải xấu trước khi budget trở thành giới hạn. Vẫn cần cả hai: breaker bảo vệ từng provider theo sức khỏe quan sát được, còn budget hạn chế retry khi chưa đủ mẫu hoặc breaker cấu hình sai.

### 3.2. Timeout 30 giây: xem availability trước p95

| Băng | Timeout | Availability | Good/total turns | Give-up reasons | p95 lượt thành công (s) |
|---|---:|---:|---:|---|---:|
| G4 | 6 | 1.0000 | 2174/2174 | Không | 5.604 |
| G4 | 30 | 1.0000 | 2174/2174 | Không | 5.608 |
| G6 | 6 | 0.9996 | 2384/2385 | no_provider_available: 1 | 5.982 |
| G6 | 30 | 0.9484 | 2262/2385 | deadline: 106; no_provider_available: 17 | 5.338 |

G4 là đối chứng chậm nhưng trả lời: tăng timeout hầu như không đổi p95 vì slow-call breaker vẫn hoạt động. G6 có region treo: timeout 30 tiêu gần hết deadline của lượt trước khi kịp fallback, làm thất bại thêm 122 lượt. p95 lại thấp hơn vì simulator chỉ tính lượt thành công; các lượt chậm rồi chết không còn nằm trong mẫu latency. Timeout nên dựa trên phân bố latency khỏe, deadline còn lại của cả workflow và thời gian cần cho fallback; không lấy 30 giây chờ của user làm timeout cho mỗi attempt.

### 3.3. Bỏ lọc tool calling

| G6 | Availability | Incompatible routes | Give-up vì output không tương thích |
|---|---:|---:|---:|
| Có lọc khả năng | 0.9996 | 0 | 0 |
| Không lọc | 0.8948 | 251 | 251 |

Model nhỏ không hỗ trợ tool nên 251 lượt nhận output không dùng được cho bước hoàn tiền, availability giảm 10.48 điểm phần trăm. Vì vậy fallback phải đáp ứng tính năng của bước đang chạy; model trả lời được văn bản chưa chắc thực hiện được thao tác sản phẩm cần.

## 4. Workflow hoàn tiền

Nguồn: `workflows.json` và mốc `part_d_runs/run_001/seed_25.json`.

| Executor | Completion | Crashes | Refund trùng | Email trùng | Refund mất | Overpaid (cent) | Wasted LLM/crash |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive | 1.0000 | 81 | 128 | 81 | 0 | 1574200 | 1.123 |
| yours | 1.0000 | 66 | 0 | 0 | 0 | 0 | 0.303 |

Mỗi seed có 500 workflow. Seed 26/27 cũng completion 1.0000, không refund/email trùng hoặc refund mất; wasted LLM/crash lần lượt 0.241/0.338, đều ≤0.6.

Idempotency key ổn định theo session/step giữ cho payment/email chỉ có một effect kể cả response mất hoặc worker chết ngay sau commit. Chỉ key chưa đủ vì worker vẫn tính lại LLM/read nếu không có checkpoint. Chỉ checkpoint chưa đủ vì có khoảng trống giữa side effect thành công và lưu checkpoint: restart sẽ gọi payment lại. Ghi checkpoint trước payment còn nguy hiểm hơn vì worker sau có thể bỏ qua một refund chưa thực hiện. Executor chỉ checkpoint sau thành công, retry cùng key và để `WorkerCrash` thoát ra cho runner khởi động worker mới.

## 5. Alerting và error budget

Nguồn: `slo.json`, mốc `part_e_runs/run_001/`. Dữ liệu có 43.200 phút; SLO 99.5%/30 ngày.

| Sự cố | Mong đợi | Naive alerter | Burn-rate alerter | Delay burn-rate (phút) |
|---|---|---|---|---:|
| checkout_bug | page | page sau 1 phút | page | 27 |
| provider_outage | page | page ngay | page | 4 |
| deploy_blip | none | page sai | không page | — |
| slow_leak | ticket | không ticket | ticket, không page | 1337 |
| degraded_evening | page | page sau 214 phút | page | 291 |
| night_spike | none | page sai | không page | — |
| small_bump | none | page sai | không page | — |

Naive có 3 false page; burn-rate có 0 false page và đạt mọi thời hạn public. Prefix sums cho truy vấn O(1); chỉ firing khi cả cửa sổ dài và ngắn đạt ngưỡng, gom các phút liên tiếp thành một episode.

Tổng request 25,901,755; bad 55,618; allowed bad 129,508.8; availability 99.7853%. Budget đã dùng **42.95%**, còn **57.05%**: **không freeze release**. `small_bump` tiêu khoảng 1.385% budget tháng; burn 1h cao nhất 8.225× (<14.4×), burn 6h cao nhất 1.911× (<6×). Nó không đạt ngưỡng page dù tỷ lệ lỗi ngắn hạn vượt 5%, nên không cần đánh thức on-call cho bump tự hồi phục này.

## 6. Postmortem: G2 với client naive, blameless

![Attempts và call success ratio của naive/resilient](gameday/G2_overload_storm.png)

**Tóm tắt (3 câu).** Tại t=120, alpha mất 75% năng lực trong 180 giây, làm hàng đợi tăng và request bắt đầu timeout. Retry ba tầng của v1 tiếp tục tạo tải lớn, còn request đã timeout vẫn chiếm công suất phía server. Provider hồi phục ở t=300 nhưng hệ thống chỉ đạt lại ngưỡng recovery ở t=455; client resilient giữ availability 100% trên cùng băng nhờ breaker, budget và fallback.

**Ảnh hưởng.** **1,285/2,362 lượt user thất bại** (54.40%); p95 lượt thành công 15.034 giây. Recovery cần thêm **155 giây** sau khi provider phục hồi, tức 335 giây kể từ trigger. CSV có call lỗi từ giây 142 đến 468. Giả sử 4 lượt/s đều trong 30 ngày và SLO 99.5%, budget tháng là 51,840 lượt xấu; G2 tiêu **2.479%**, còn 97.521% nếu tháng chỉ có sự cố này.

**Timeline.** Khoảng `[start, end)` tính bằng giây ảo; attempts/s là trung bình, success ratio đo logical call hoàn tất.

| Khoảng t | Sự kiện | Attempts alpha/s | Call tốt / hoàn tất | Call success |
|---|---|---:|---:|---:|
| [100,120) | Trước sự cố | 8.15 | 160/160 | 100% |
| [120,140) | Mất GPU; tải retry bắt đầu tăng | 29.05 | 51/51 | 100% |
| [150,170) | Retry storm đã hình thành | 155.75 | 0/93 | 0% |
| [280,300) | Provider vẫn suy giảm | 154.85 | 0/83 | 0% |
| [300,320) | GPU hồi phục nhưng backlog còn | 27.25 | 0/28 | 0% |
| [400,420) | Tải retry tiếp tục duy trì lỗi sau restore | 74.25 | 0/77 | 0% |
| [455,485) | Cửa sổ 30 giây đầu đạt ≥95% call tốt | 10.87 | 352/368 | 95.65% |
| [500,520) | Trở về gần tải nền | 9.00 | 186/186 | 100% |

Nguồn: `part_f_runs/run_001/postmortem_G2.json` và CSV `gameday/naive_G2_overload_storm_timeseries.csv`. Trong 20 giây đầu, request đang xếp hàng chưa nằm trong mẫu hoàn tất nên success ratio vẫn 100%.

**Trigger và root cause.** Trigger là alpha mất 75% công suất. Root cause phía client là retry app × gateway × SDK tối đa 36 attempt/call, delay cố định, không budget/breaker/fallback. Timeout không hủy công việc server: request cũ vẫn chạy trong khi retry tạo tải mới, backlog tăng latency, latency gây thêm timeout và retry. Vòng lặp tự duy trì sau khi GPU trở lại gây metastable failure.

**Điều giúp và điều làm tệ hơn.** Giới hạn attempt/deadline cuối cùng giúp tải cũ cạn đi, nhưng retry đã tạo 34,475 attempt cho 3,481 logical call và 28,381 vi phạm retry-after. Resilient dùng budget/breaker/fallback để giảm amplification xuống 1.046, cost/good turn từ 4.627 xuống 2.133. Nguyên nhân nằm ở thiết kế tương tác giữa các lớp retry.

| # | Action item | Loại | Owner theo vai trò | Cách kiểm chứng |
|---|---|---|---|---|
| 1 | Giữ retry ở một lớp, có full jitter, budget và tôn trọng retry-after | prevent | Nhóm client SDK | G1/G2 amplification ≤1.6, 0 retry-after violations trên nhiều seed |
| 2 | Dùng sliding-window breaker, bắt slow call, giới hạn HALF_OPEN probe | mitigate | Nhóm nền tảng agent | G2 recovery ≤30s; G4 p95 ≤10s; kiểm tra stale generation và probe cap |
| 3 | Theo dõi attempt/logical-call, provider timeout, trạng thái breaker và burn-rate | detect | Nhóm SRE | Không false page trên blip; mọi labelled page/ticket đúng thời hạn |
| 4 | Kiểm thử crash sau payment/email trước khi rollout | prevent | Nhóm workflow/QA | 500 workflow/seed, duplicate/lost effect =0, completion ≥99% |

## 7. Điểm yếu còn lại

G2 seed 26 vẫn có p95 **10.626 giây** dù availability 100%. Fallback sang beta cũng đắt hơn mỗi call (1.4 so với 1.0 của alpha); G6 cost/good turn là 2.208. Hướng cải thiện là thử admission control, ngưỡng slow-call và định tuyến theo tải, kiểm chứng nhiều seed trước khi đổi cấu hình. Khi mọi provider sập lâu hơn stale window, cần luồng chuyển người xử lý hoặc xử lý bất đồng bộ cho câu mới/cá nhân.

## 8. Cache: Part G

Nguồn: `part_g_runs/run_001/`.

| Client | Availability | FAQ availability | Cache hit | Stale served | Wrong | Outdated | Cost/good turn | PASS C1 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Resilient, không cache | 0.8373 | 0.8424 | 0.000 | 0 | 0 | 0 | 1.386 | Không |
| Cached, cấu hình chốt | 0.9124 | 0.9645 | 0.592 | 192 | 0 | 2 | 0.955 | Có |

| Cache setting | Giá trị | Lý do |
|---|---:|---|
| similarity_threshold | 0.90 | Wrong =0; ngưỡng 0.80 có 181 other-question hit, 0.97 chỉ hit 0.499 ở seed 25 |
| ttl_s | 30 | Giới hạn tuổi answer được serve trực tiếp; outdated 2/4/7 trên ba seed, đều ≤15 |
| max_stale_s | 300 | Cứu 192 stale hit ở seed 25; tắt stale làm FAQ availability giảm 0.9645 → 0.8529 |
| max_entries | 500 | Có giới hạn dung lượng bằng LRU; eviction được test riêng, không tăng vô hạn theo traffic |

### 8.1. Thí nghiệm ngưỡng

Giữ TTL 30, stale 300. Ngưỡng 0.80/0.90/0.97 cho hit ratio **0.610/0.592/0.499**, wrong **181/0/0**, cost/good turn **1.016/0.955/1.018**. Ngưỡng thấp nhận câu khác ý; ngưỡng quá cao bỏ lỡ paraphrase. Trace ở `part_f_runs/run_001/cache_threshold_080_diagnostic/` ghi nhận các cặp trả nhầm: chính sách/thời gian hoàn tiền **77**, ship nội thành/đi tỉnh **81**, phương thức thanh toán/COD **13**, đổi size/màu **10**.

### 8.2. Thí nghiệm TTL

Giữ threshold 0.90, stale 300. TTL 30/60/300 cho hit ratio **0.592/0.652/0.731**, outdated **2/3/95**, cost/good turn **0.955/0.915/0.863**. TTL 60 cũng PASS; chọn 30 để ưu tiên độ tươi, vẫn vượt hit tối thiểu 50%. Webhook chỉ xử lý thay đổi được thông báo; phí ship đổi im lặng ở t=480 nên TTL phải buộc refresh khi provider khỏe.

### 8.3. Thí nghiệm stale-if-error

Giữ threshold 0.90, TTL 30. Tắt stale làm FAQ availability **0.9645 → 0.8529**, hit **0.592 → 0.481**, stale served **192 → 0**. Stale giúp vượt outage 120 giây, chỉ serve sau khi inner client GiveUp; webhook và prompt scope vẫn có hiệu lực. Nếu nguồn đổi im lặng trong outage, answer có thể cũ đến hết tổng tuổi 330 giây.

Seed 26/27 cũng PASS: FAQ availability **0.9540/0.9627**, hit **0.591/0.591**, wrong **0/0**, outdated **4/7**. Không cache câu cá nhân dù tách user vì trạng thái đơn/tiền/điểm có thể thay đổi; tách user không đảm bảo độ tươi. Khi cache che outage, cần theo dõi provider error/timeout, breaker OPEN, tỷ lệ stale served và tuổi answer độc lập với availability cuối.
