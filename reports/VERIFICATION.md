# Bước 10 — Kiểm tra bài nộp

**Repo:** [Track3-Day25-2A202602704-Pham-Quang-Dat](https://github.com/datpq-alpha/Track3-Day25-2A202602704-Pham-Quang-Dat)

**Nhánh:** `main` · **Commit mã nguồn kiểm chứng:** `7a37bed`

Đã xác nhận repo public bằng truy cập API không đăng nhập. Họ tên **Phạm Quang Đạt**, MSSV **2A202602704** đã điền trong REPORT; báo cáo giữ đủ 8 mục theo rubric.

## Kết quả kiểm tra lại

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ pytest | **104 pass** |
| Test tính điểm của grader | **76/76 pass** |
| Game Day G1–G6, seed 25/26/27 | **18/18 PASS** |
| Cache C1, seed 25/26/27 | **3/3 PASS** |
| Workflow, 500 session/seed | **3/3 PASS**, không duplicate/lost effect |
| SLO public 30 ngày | **PASS**, 0 false page |
| Điểm tự động | **84/88**; 4 điểm SLO ẩn chờ giảng viên |
| Báo cáo | Đủ 8 mục; tối đa 12 điểm chấm tay |

## Bằng chứng

- `reports/scoreboard.json`: kết quả grader ba seed.
- `reports/verification_runs/run_002/`: log pytest/grader và kiểm tra thông tin báo cáo của lượt này.
- `reports/verification_runs/run_001/`: lần kiểm chứng trên checkout sạch, môi trường mới, lint/type-check và checksum snapshot.
- `reports/gameday/G2_overload_storm.png`: hình postmortem.
- Các thư mục `part_d_runs`, `part_e_runs`, `part_f_runs`, `part_g_runs`: kết quả và cấu hình thí nghiệm đã lưu riêng.

Code đã làm pass Ruff và Mypy. Lint toàn repo còn ba lỗi nguyên bản trong file cấm sửa: `SIM103` ở `sim/config.py`, `RUF046` ở `slo/data.py`, `C408` ở `tests/test_breaker.py`; chi tiết trong `run_001/ruff_full.log`.

`vlearn.md` không nằm trong Git. Không chạy `make clean` sau khi chuẩn bị bài vì lệnh này xóa artifacts.

```powershell
python -m pytest -q -p no:cacheprovider
python scripts/grade.py --seeds 25,26,27 --out reports/scoreboard.json
```
