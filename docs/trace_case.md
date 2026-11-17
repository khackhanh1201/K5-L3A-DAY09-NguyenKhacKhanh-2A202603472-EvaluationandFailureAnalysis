# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case: FM-03 trên C-002

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55               # trial lỗi trong baseline
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11   # cùng lỗi, mọi seed
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55               # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55`, trial lỗi duy nhất của `swarm` trên 14 item × 5 seed (`pass_rate` 0.9857), nằm trong baseline `E-swarm-…` (`src/reports/baseline_v1.json`). Cùng lỗi lặp lại ở `seeded_regression C-002@11..55`. |
| Triệu chứng | Lab 8 grader FAIL: `status resolved != denied`. Ledger `refund_vnd = 20000`, `refund_count = 1`, label `0` / `0`. `DbFactKept` fail (1 event override). Ở `seeded_regression`, reply nói "đã hoàn 20.000đ cho đơn O-202", khớp ledger nhưng ledger sai. |
| Bước sai đầu tiên | Event 3 `model_override` `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng: chỉ cho các tool đọc (`lookup_order`, `lookup_policy`, `compute_compensation`), `facts: {}`. Event 2 `investigator` đúng: `lookup_order` trả O-202 với `delay_days: 2` từ DB. Event 3 ghi đè 2 bằng 5 lấy từ ticket ("Đơn giao trễ 5 ngày"). Event 4 `quote` áp `SHIP-LATE-03` → 20.000đ chỉ là hệ quả: tính đúng trên một dữ kiện đã sai. |
| Failure mode | FM-03 ticket_trust (layer model/prompt) |
| Đối chứng | `fixed C-002@55` (và `swarm C-002@11`): không có event `model_override`; event 3 là `quote {"amount_vnd": 0, "reason": "no_entitlement"}`; status `denied`, ledger 0. Lỗi của `swarm` chỉ bật khi `seed % 5 == 0`, nên chỉ seed 55 trong bộ 5 seed bị dính. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_c002_ticket_trust_is_caught[swarm-55 / seeded_regression-11]` khẳng định có `model_override {"delay_days": 5}`, ledger ≠ label và Lab 8 FAIL; `test_c002_db_fact_kept_when_fixed[fixed-11 / fixed-55 / swarm-11]` khẳng định không override, ledger 0, status `denied`. Đã chạy: 5/5 pass, tức là test bắt được lỗi trên variant lỗi và không báo nhầm trên `fixed`. Ở mức eval set, item E-002 (`provenance.from_trace = "swarm C-002@55"`) chấm bằng `db_fact_kept` và `refund_amount_correct`. |
| Chưa chắc chắn | Trace không cho biết vì sao reference tin ticket ở đúng seed 55: đó là quy tắc `seed % 5 == 0` cài sẵn trong MockLLM, không phải hành vi đo được của một LLM thật. Với LLM thật, tần suất lỗi có thể khác 1/5 và phụ thuộc cách viết ticket. Biến thể `quiet_override` (tin ticket mà không ghi event) sẽ qua `DbFactKept`; khi đó chỉ `refund_amount_correct` và `pass_rate` còn bắt được. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
