# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend replay, phán quyết judge lưu sẵn trong CSV). Lớp positive = **FAIL** (việc của judge là tìm lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok (`judge_tone_public.csv`) | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **dùng**, chỉ làm metric theo dõi, không blocking |
| helpful (`judge_helpful_public.csv`) | 100 | 0.375 | 1.000 | **0.300** | **Không** (κ và R dưới sàn, exit 1) | **loại**, không được làm gate |

Ma trận nhầm lẫn (FAIL = positive):

| | tp | fp | fn | tn | specificity | Tỉ lệ FAIL quan sát → hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 66/70 = 0.943 | 0.28 → 0.30 |
| helpful | 9 | 0 | 21 | 70 | 70/70 = 1.000 | 0.09 → 0.30 |

## ≥5 case audit thủ công

Tone có 10 bất đồng, helpful có 21 (cả 21 đều là judge PASS, người FAIL). Bảng dưới gồm toàn bộ 10 ca tone và các nhóm đại diện của helpful.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em", thêm "nha" là quá suồng sã với khách khiếu nại. **Rubric:** thêm luật xưng hô bắt buộc "LogiX – anh/chị"; xưng "em/bạn" hoặc dùng "nha/nhé" ⇒ FAIL. Thêm H-008 làm ví dụ FAIL trong prompt. |
| 2 | tone H-017 "Dạ, bạn ơi LogiX đã hoàn…" | PASS | FAIL | Người | Cùng luật xưng hô như #1. |
| 3 | tone H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge bị "Dạ, vui lòng" đánh lừa. **Rubric:** câu mệnh lệnh hoặc chặn khách liên hệ ("không cần nhắn thêm") ⇒ FAIL dù mở đầu lịch sự. |
| 4 | tone H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống. Đây là lỗi nội dung, không phải giọng văn. **Rubric:** tách khỏi tone; hứa hẹn tiền chuyển cho grader code (so reply với ledger, FM-08). |
| 5 | tone H-070 "…ạ 😂😂" | PASS | FAIL | Người | **Rubric:** emoji trong ngữ cảnh khiếu nại ⇒ FAIL. |
| 6 | tone H-094 "Da, LogiX da hoan…" (mất dấu) | PASS | FAIL | Người | **Rubric:** tiếng Việt không dấu hoặc dịch máy ⇒ FAIL. |
| 7 | tone H-042 "…đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. **Rubric:** ghi rõ xin lỗi là tùy chọn; ngắn mà đủ ý (số tiền, đơn, thời gian) là PASS. |
| 8 | tone H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | Quy định CS của LogiX cho phép dùng "refund". **Rubric:** thêm danh sách từ tiếng Anh được phép (refund, ship, voucher). |
| 9 | tone H-081 "…đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Người đọc nhầm ticket nên nhãn sai. **Hành động:** sửa nhãn người thành FAIL trong bản CSV v2 (không sửa file công khai đang dùng để chấm), ghi lý do trong cột note. Đây là bằng chứng cần ≥2 người gán nhãn cho mỗi dòng. |
| 10 | tone H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | Hòa (lỗi nhẹ) | Lặp "Dạ" do lỗi gõ. **Rubric:** lỗi gõ đơn lẻ không đổi nghĩa ⇒ PASS; judge đang quá khắt khe. |
| 11 | helpful HL-015, HL-020, HL-062, HL-087, HL-100 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (note: ledger 40.000đ / 35.000đ / …) | PASS | FAIL | Người | Reply nói **số tiền khác ledger** (FM-08). Judge chỉ thấy văn bản, không thấy ledger, nên **không thể** chấm đúng. **Hành động:** bỏ "đúng số tiền" khỏi rubric helpful; tiêu chí đó do grader code `reply_matches_ledger` chấm (M3). |
| 12 | helpful HL-016, HL-028, HL-043, HL-053, HL-090, HL-098 (2–3 câu xin lỗi bọc quanh một số tiền sai so với ledger) | PASS | FAIL | Người | Vừa sai tiền vừa **thiên vị câu dài**: lời xin lỗi lặp lại làm judge cho qua. **Rubric:** chấm "có đủ thông tin khách cần" (số tiền, đơn, bước tiếp theo); câu lặp không cộng điểm, độ dài không phải tiêu chí. Thêm 2 ví dụ FAIL dài vào prompt. |
| 13 | helpful HL-047, HL-091, HL-097 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả (hoàn bao nhiêu hay bị từ chối) và không có bước tiếp theo. **Rubric:** reply không nêu trạng thái và số tiền ⇒ FAIL. |

## Kết luận

- **tone_ok dùng được.** κ 0.757, P 0.857, R 0.800, đều trên sàn. Nhưng 6/10 bất đồng đều cùng một kiểu: judge coi suồng sã là thân thiện (fn = 6). Sửa rubric theo #1–#6, rồi calibrate lại trên nhãn mới trước khi tin. Chỉ dùng làm metric theo dõi, không blocking: giọng văn không làm mất tiền.
- **helpful bị loại.** Recall 0.30: judge bỏ sót 21/30 reply mà người đánh FAIL (fn = 21, tp = 9). κ 0.375 dưới sàn 0.6. Precision 1.0 không cứu được judge này: nó không bao giờ báo nhầm, nhưng cũng hầu như không bao giờ báo lỗi. Tỉ lệ FAIL quan sát 0.09 trong khi hiệu chỉnh Rogan-Gladen ra 0.30. Nếu dùng làm gate, chất lượng sẽ bị đánh giá tốt hơn thực tế khoảng 3 lần, và các PR làm reply sai số tiền vẫn lọt.
- **Nguyên nhân gốc của helpful:** phần lớn ca bỏ sót (18/21) là reply nói số tiền khác ledger. Judge chỉ đọc văn bản, nên không thể kiểm được điều này. Đúng quy tắc của bài: **tiền luôn chấm bằng code**. Phần này chuyển sang `reply_matches_ledger` (FM-08); phần "đủ thông tin" còn lại mới đáng thử lại với rubric mới.
- **Rủi ro còn lại:**
  - Judge chỉ được kiểm trên dữ liệu replay đã công khai, và rubric được sửa ngay trên chính 100 dòng này, nên số liệu sau khi sửa sẽ lạc quan hơn thực tế. Cần một tập nhãn người mới, chưa từng xem, để có held-out thật.
  - Chỉ 100 dòng, trong đó 30 FAIL, nên khoảng tin cậy của P/R còn rộng.
  - H-081 cho thấy nhãn người cũng sai được; cần 2 người gán nhãn mỗi dòng và đo κ giữa hai người.
  - Judge replay không thay đổi giữa các lần chạy; judge LLM thật có nhiễu theo seed và theo phiên bản model, nên phải calibrate lại mỗi khi đổi model hoặc prompt.
