# Bước 7 — Part D: Workflow hoàn tiền

Hoàn thiện `src/gameday_lab/workflows/executor.py`:

- Idempotency key là SHA-256 của cặp `(session_id, step)` được mã hóa JSON, ổn định qua retry/restart và không nhập nhằng khi ID chứa ký tự phân cách. Không thêm amount/order vào key: thay payload của cùng thao tác phải bị service báo conflict, thay vì tạo một khoản hoàn tiền mới.
- Retry tối đa 5 attempt/step, chỉ bắt `ServiceError` và `ServiceTimeout`; lỗi khác và `WorkerCrash` được truyền ra ngoài.
- Chạy đủ 5 step theo thứ tự; chỉ ghi checkpoint sau khi step thành công. Worker mới nạp kết quả đã checkpoint rồi chạy tiếp.

## Kết quả 500 workflow, seed 25

| Executor | Completion | Crashes | Refund trùng | Email trùng | Refund mất | Overpaid (cent) | LLM lãng phí/crash |
|---|---:|---:|---:|---:|---:|---:|---:|
| Naive | 100% | 81 | 128 | 81 | 0 | 1.574.200 | 1,123 |
| Yours | 100% | 66 | 0 | 0 | 0 | 0 | 0,303 |

Các seed 26/27 cũng hoàn tất 100%, không có refund/email trùng, refund mất hay overpaid; LLM lãng phí/crash lần lượt 0,241 và 0,338. Tất cả đều dưới giới hạn 0,6. Bảy test gốc của Part D và Ruff đều pass.

Chỉ idempotency key chưa đủ: tránh side effect trùng nhưng vẫn chạy lại LLM/read sau crash, tăng chi phí. Chỉ checkpoint chưa đủ: payment có thể đã chạy nhưng worker chết trước lúc lưu kết quả, dẫn đến gọi payment lần nữa. Ghi checkpoint trước payment có thể đánh dấu hoàn thành một khoản tiền chưa được chuyển; worker sau sẽ bỏ qua nó và làm mất refund.

Kết quả thường: `reports/workflows.json`. Mốc giữ riêng: `reports/part_d_runs/run_001/`, gồm JSON từng seed, fault profile, số attempt và bản sao nguồn kèm checksum. Các số này áp dụng cho mô hình single-worker-per-session của runner; checkpoint không tự cung cấp khóa phân tán cho nhiều worker cùng xử lý một session.

```powershell
python -m pytest tests/test_executor.py -q -p no:cacheprovider
python scripts/run_workflows.py --executor both
```
