# Vocabulary trimming experiment — 2026-10-22

ทดลองบน RTX 3050 Laptop, PyTorch 2.6.0+cu124, Transformers 5.14.1, FP32
ใช้ 10 หน้าย่อยแรกของ Naver ตอนเดิม ภาพ 0–4 เป็น calibration และภาพ 5–9 เป็น held out
นี่เป็นผลการทดลองครั้งแรกก่อนเปลี่ยน runtime ไม่มีการฝึกเพิ่ม
ปัจจุบันติดตั้งฐานแปล trimmed และใช้ OCR FP16 แล้ว ดู [สถานะล่าสุด](OPTIMIZATION.md)

| ส่วน | เดิม | หลังตัด | น้ำหนัก FP32 ที่ประหยัด |
|---|---:|---:|---:|
| M2M100 vocabulary | 128,112 tokens | 70,193 tokens | 237.24 MB (12.26% ของพารามิเตอร์ที่โหลดจริง) |
| EasyOCR recognizer charset | 1,008 ตัวอักษร | 121 ตัวอักษร | 0.912 MB (5.68% ของ recognizer) |

MB ในหน้านี้เป็นฐานสิบ จำนวนพารามิเตอร์ MT ที่นับจากโมเดลที่โหลดจริงคือ
483,905,536 → 424,596,480 แม้ model ID จะชื่อ `m2m100_418M`
ส่วน recognizer คือ 4,015,729 → 3,787,770 พารามิเตอร์

## โมเดลแปล

เลือกเก็บชิ้นคำ Latin/Hangul ตัวเลข เครื่องหมาย สัญลักษณ์ special tokens
และ token ที่พบในข้อความ calibration โดยยังใช้ SentencePiece เดิมและ remap ID
ตรวจแล้วว่าคะแนน logits ของ token ที่เก็บไว้ตรงกับเดิม และบันทึก/โหลดโมเดลกลับได้

- ข้อความทั้ง 24 ข้อความไม่มี input token ที่ถูกตัดออก
- ผลแปลเหมือนเดิม 23/24 ข้อความ; เฉพาะ held out เหมือนเดิม 14/15 ข้อความ
- ตัวอย่างที่เปลี่ยน: `맞아요` จาก `is right.` เป็น `right is.`
- เวลา generate รวม 24 ข้อความหลัง warm-up: 4.083 → 3.376 วินาที
- เฉพาะ held out: 2.361 → 2.085 วินาที
- Peak CUDA allocated ในรอบ generate: 1,978.50 → 1,737.13 MB
- ไฟล์ trimmed safetensors: 1,698.45 MB ไม่รวม tokenizer และ ID map

เวลาเป็นการวัดรอบเดียว ไม่รวมโหลดโมเดล OCR ตรวจจับข้อความ หรือ inpainting
แม้ logits ที่เก็บไว้ตรงกัน การตัดตัวเลือกออกเปลี่ยน softmax/beam search ได้
ผลแปลจึงไม่รับประกันว่าจะเหมือนเดิมทุกประโยค

## OCR

`korean_g2` มีเฉพาะ Hangul และ ASCII อยู่แล้ว หากเก็บเกาหลีกับอังกฤษครบจะตัดไม่ได้
การทดลองแบบเข้มข้นจึงเก็บ ASCII ทั้งหมดและตัวอักษรที่ OCR พบในภาพ calibration 5 ภาพ
ตัดเฉพาะแถวใน prediction head และสร้าง CTC converter ใหม่ โดยเก็บ blank ID 0
ตรวจว่า projection ของแถวที่เก็บไว้ตรงกัน และ checkpoint โหลดกลับได้

- Calibration: ผล OCR เหมือนเดิม 5/5 ภาพ
- Held out: เหมือนเดิมเพียง 1/5 ภาพ โดยภาพที่เหมือนเป็นภาพไม่มีข้อความ
- พบตัวอักษรในผล OCR เดิมของ held out ที่ไม่ได้เก็บไว้ 32 ตัว ทำให้หลายคำเพี้ยน
- เวลา recognition ของ held out: 0.276 → 0.348 วินาที ไม่พบข้อได้เปรียบด้านความเร็วในรอบนี้
- CRAFT detector ขนาด 83.15 MB ไม่มี vocabulary จึงไม่เปลี่ยน; เมื่อรวม detector ประหยัดไม่ถึง 1%

**ข้อเสนอ:** MT trim มีประโยชน์เรื่องขนาด แต่ต้องวัดกับข้อความจากหลายเรื่องและคำแปลอ้างอิงก่อนใช้จริง
ส่วน OCR ไม่ควรใช้ charset ที่ตัดตามภาพเพียงไม่กี่หน้า เพราะประหยัดน้อยและเสียการครอบคลุมตัวอักษรมาก
ข้อมูลอ้างอิงในครั้งนี้เป็นผลโมเดลเดิม ไม่ใช่ ground truth จากคน จึงวัด agreement ไม่ใช่ accuracy

## ไฟล์และการทำซ้ำ

- [ผลเทียบรายภาพ](work/vocab-trim-20261022/review.html)
- [รายงานพร้อมข้อความและเวลา](work/vocab-trim-20261022/report.json)
- `work/vocab-trim-20261022/translation/`: trimmed model, original tokenizer, `id-map.json`
- `work/vocab-trim-20261022/ocr/`: recognizer weights และ `characters.json`

Artifacts อยู่ใน `work/` จึงไม่เข้า Git และต้องสร้างใหม่บนเครื่องอื่น
สคริปต์ใช้โมเดลใน cache เท่านั้น ต้องมีภาพ, OCR cache และโมเดลเดิมก่อน
เลือก output ใหม่ที่ยังไม่มีอยู่เพื่อป้องกันการเขียนทับ:

```powershell
translator/.venv/Scripts/python.exe translator/test_vocab_trim.py
translator/.venv/Scripts/python.exe translator/experiment_vocab_trim.py --out translator/work/vocab-trim-next
```

MT artifact ไม่ใช่คู่ model/tokenizer ที่เรียกใช้แทนรุ่นเดิมได้ทันที:
ต้องใช้ tokenizer เดิม, remap input IDs, forced English ID และ output IDs
ตามฟังก์ชัน `generate` ใน [experiment_vocab_trim.py](experiment_vocab_trim.py)
หาก input มี token ที่ถูกตัด ฟังก์ชันจะหยุดพร้อมข้อผิดพลาดเพื่อให้กลับไปใช้โมเดลเดิม
ส่วน OCR checkpoint ต้องใช้ charset/CTC converter ที่ตรงกันตามโค้ดทดลอง

สำหรับฝึก LoRA ภายหลัง ต้องใช้ trimmed base และ ID mapping ชุดเดิมทั้งตอนฝึกและ inference
