# ASR Quality Evaluation — general

**Samples evaluated:** 22  
**LoRA adapter available:** Yes  

---

## Summary

| Metric | Base Whisper | LoRA Fine-tuned | Delta |
|--------|-------------|-----------------|-------|
| **WER** (lower=better) | 1.2361 | 1.1922 | -0.0439 (✓ better) |
| **CER** (lower=better) | 0.8689 | 0.9176 | +0.0487 (✗ worse) |
| **Med. Term Acc** (higher=better) | 1.0000 | 1.0000 | 0.0000 (=) |

### Dictation samples (n=10)

| Metric | Base | LoRA | Delta |
|--------|------|------|-------|
| WER | 0.6247 | 0.7714 | +0.1467 (✗ worse) |

### Ambient samples (n=12)

| Metric | Base | LoRA | Delta |
|--------|------|------|-------|
| WER | 1.7455 | 1.5429 | -0.2026 (✓ better) |

---

## Per-Sample Results

| Sample | Mode | Base WER | LoRA WER | Base CER | LoRA CER | Base MTA | LoRA MTA |
|--------|------|----------|----------|----------|----------|----------|----------|
| 224889 | dictation | 0.5625 | 0.7794 | 0.4316 | 0.7178 | 1.0000 | 1.0000 |
| 225981 | dictation | 0.6831 | 0.8045 | 0.5314 | 0.7875 | 1.0000 | 1.0000 |
| 226537 | dictation | 0.5828 | 0.6405 | 0.4872 | 0.6401 | 1.0000 | 1.0000 |
| 226680 | dictation | 0.5895 | 0.7214 | 0.4843 | 0.7124 | 1.0000 | 1.0000 |
| 226748 | dictation | 0.5078 | 0.5676 | 0.4025 | 0.5551 | 1.0000 | 1.0000 |
| 226806 | dictation | 0.6649 | 0.8474 | 0.5038 | 0.8390 | 1.0000 | 1.0000 |
| 226974 | dictation | 0.6577 | 0.8586 | 0.5291 | 0.8546 | 1.0000 | 1.0000 |
| 25835 | dictation | 0.6523 | 0.7819 | 0.5606 | 0.7779 | 1.0000 | 1.0000 |
| 26542 | dictation | 0.6398 | 0.8509 | 0.4525 | 0.8388 | 1.0000 | 1.0000 |
| 27093 | dictation | 0.7067 | 0.8622 | 0.5669 | 0.8564 | 1.0000 | 1.0000 |
| 128579_7321392_5_157520 | ambient | 1.7563 | 1.4479 | 1.1527 | 0.9555 | 1.0000 | 1.0000 |
| 138680_7333782_3_7333782 | ambient | 2.1397 | 1.7896 | 1.3627 | 1.1294 | 1.0000 | 1.0000 |
| 16425_7274335_4_151150 | ambient | 1.0293 | 0.9362 | 0.7746 | 0.7331 | 1.0000 | 1.0000 |
| 171653_7331485_3_158054 | ambient | 0.9014 | 0.9231 | 0.7219 | 0.7574 | 1.0000 | 1.0000 |
| 206551_7333161_2_157624 | ambient | 2.1054 | 1.8767 | 1.3061 | 1.1288 | 1.0000 | 1.0000 |
| 206553_7333159_2_7333159 | ambient | 1.0589 | 0.9558 | 0.8004 | 0.7506 | 1.0000 | 1.0000 |
| 211802_7286583_2_157794 | ambient | 1.7008 | 1.4321 | 1.0768 | 0.9165 | 1.0000 | 1.0000 |
| 223818_7322320_2_151496 | ambient | 1.2267 | 1.0844 | 0.8070 | 0.7625 | 1.0000 | 1.0000 |
| 224938_7286318_1_151007 | ambient | 2.7191 | 2.3090 | 1.7462 | 1.4637 | 1.0000 | 1.0000 |
| 225470_7325718_1_7325718 | ambient | 0.9052 | 0.9313 | 0.7364 | 0.7834 | 1.0000 | 1.0000 |
| 227512_7333052_1_157675 | ambient | 2.3154 | 1.9799 | 1.5221 | 1.2851 | 1.0000 | 1.0000 |
| 227534_7334641_1_7334641 | ambient | 3.0880 | 2.8488 | 2.1594 | 1.9422 | 1.0000 | 1.0000 |

---

## Worst-Error Samples (Base Model)

### 227534_7334641_1_7334641

**WER:** 3.0880 | **CER:** 2.1594

**Reference (first 300 chars):**
> The patient is being seen for worsening neck pain after a recent auto accident, with symptoms improving initially following previous injuries in January 2026 but now exacerbated. History of Present Illness The patient reports worsening neck and back pain, rating it as 9 out of 10, which started imme

**Base hypothesis (first 300 chars):**
> You filled out our giant online intake AC. So you're seeing me for valuation from this, for injuries from this auto accident, 227, 26. You are left-handed. Yes. And self-employed with Uber? Yes, Uber and Lyft. Uber and Lyft driver. All right, the accident was 227. You were driving, I assume? Yes, so

**LoRA hypothesis (first 300 chars):**
> You filled out our giant online and take a seat. You're seeing me for valuation from this for injuries from this auto accident to twenty seven twenty six. You are left handed. And self-employed with Uber. Yes. Uber and Lyft driver. All right. The accident was to twenty seven. You were driving, I ass

### 224938_7286318_1_151007

**WER:** 2.7191 | **CER:** 1.7462

**Reference (first 300 chars):**
> The patient is experiencing bothersome right shoulder, lumbar spine, and right knee symptoms, including pain, with limited mobility and tenderness upon palpation. History of Present Illness The patient is experiencing persistent symptoms of pain in his right shoulder, low back, and right knee, with 

**Base hypothesis (first 300 chars):**
> All right, so you're sending me for follow-up for this work injury from December of 25. Last time I saw you, we continued treatment for your low back, right shoulder, left wrist, left hand, right knee, right ankle, right foot. I ordered some MRI scans of the right shoulder, right knee, and low back.

**LoRA hypothesis (first 300 chars):**
> All right, so for follow up for this work injury, December 25. Last time I saw you, continued treatment for your low back, right shoulder, left wrist, left hand, right knee, right ankle, right foot. I ordered some MRI scans of the right shoulder, right knee, and low back. Looks like those are schedu

### 227512_7333052_1_157675

**WER:** 2.3154 | **CER:** 1.5221

**Reference (first 300 chars):**
> The patient presents with acute muscle metastatic sprain, strain of cervical and thoracic spine, post-traumatic, as well as bilateral shoulder sprains, post-traumatic, resulting in severe pain in their neck, back, and shoulders. History of Present Illness The patient reports experiencing aching, thr

**Base hypothesis (first 300 chars):**
> Hey, Mr. Clark. How are you doing? I'm doing well, sir. I'm Dr. Herman. Nice to meet you. You're doing well. Probably better than you. Yeah, you are. I'm sorry. So let me just pull up your paperwork here. So you see me for injuries from an auto accident, 22526. You're right-handed. You're an assista

**LoRA hypothesis (first 300 chars):**
> Hey, Mr. Clark. Dr. nice to meet you. Well, probably better than you. Yeah, you are. I'm sorry. So let me just pull up your paperwork here. So you see me for injuries from an auto accident, 225.26. You're right-handed. You're an assistant supervisor at and then on the 25th. You were seat belted driv


---

*Generated by eval_asr_quality.py*