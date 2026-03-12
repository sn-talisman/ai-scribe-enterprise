# ASR Quality Evaluation — general

**Samples evaluated:** 22  
**LoRA adapter available:** Yes  

---

## Summary

| Metric | Base Whisper | LoRA Fine-tuned | Delta |
|--------|-------------|-----------------|-------|
| **WER** (lower=better) | 1.2361 | 1.1894 | -0.0467 (✓ better) |
| **CER** (lower=better) | 0.8689 | 0.9093 | +0.0404 (✗ worse) |
| **Med. Term Acc** (higher=better) | 1.0000 | 1.0000 | 0.0000 (=) |

### Dictation samples (n=10)

| Metric | Base | LoRA | Delta |
|--------|------|------|-------|
| WER | 0.6247 | 0.7930 | +0.1683 (✗ worse) |

### Ambient samples (n=12)

| Metric | Base | LoRA | Delta |
|--------|------|------|-------|
| WER | 1.7455 | 1.5198 | -0.2257 (✓ better) |

---

## Per-Sample Results

| Sample | Mode | Base WER | LoRA WER | Base CER | LoRA CER | Base MTA | LoRA MTA |
|--------|------|----------|----------|----------|----------|----------|----------|
| 224889 | dictation | 0.5625 | 0.7757 | 0.4316 | 0.7572 | 1.0000 | 1.0000 |
| 225981 | dictation | 0.6831 | 0.8128 | 0.5314 | 0.7925 | 1.0000 | 1.0000 |
| 226537 | dictation | 0.5828 | 0.6945 | 0.4872 | 0.6649 | 1.0000 | 1.0000 |
| 226680 | dictation | 0.5895 | 0.7429 | 0.4843 | 0.7287 | 1.0000 | 1.0000 |
| 226748 | dictation | 0.5078 | 0.5732 | 0.4025 | 0.5636 | 1.0000 | 1.0000 |
| 226806 | dictation | 0.6649 | 0.8807 | 0.5038 | 0.8756 | 1.0000 | 1.0000 |
| 226974 | dictation | 0.6577 | 0.8542 | 0.5291 | 0.8612 | 1.0000 | 1.0000 |
| 25835 | dictation | 0.6523 | 0.8359 | 0.5606 | 0.8543 | 1.0000 | 1.0000 |
| 26542 | dictation | 0.6398 | 0.9037 | 0.4525 | 0.8803 | 1.0000 | 1.0000 |
| 27093 | dictation | 0.7067 | 0.8563 | 0.5669 | 0.8415 | 1.0000 | 1.0000 |
| 128579_7321392_5_157520 | ambient | 1.7563 | 1.4854 | 1.1527 | 0.9682 | 1.0000 | 1.0000 |
| 138680_7333782_3_7333782 | ambient | 2.1397 | 1.9013 | 1.3627 | 1.1547 | 1.0000 | 1.0000 |
| 16425_7274335_4_151150 | ambient | 1.0293 | 0.9149 | 0.7746 | 0.7107 | 1.0000 | 1.0000 |
| 171653_7331485_3_158054 | ambient | 0.9014 | 0.9279 | 0.7219 | 0.7630 | 1.0000 | 1.0000 |
| 206551_7333161_2_157624 | ambient | 2.1054 | 1.8907 | 1.3061 | 1.1206 | 1.0000 | 1.0000 |
| 206553_7333159_2_7333159 | ambient | 1.0589 | 0.9684 | 0.8004 | 0.7535 | 1.0000 | 1.0000 |
| 211802_7286583_2_157794 | ambient | 1.7008 | 1.4044 | 1.0768 | 0.8911 | 1.0000 | 1.0000 |
| 223818_7322320_2_151496 | ambient | 1.2267 | 1.0333 | 0.8070 | 0.7445 | 1.0000 | 1.0000 |
| 224938_7286318_1_151007 | ambient | 2.7191 | 2.2060 | 1.7462 | 1.3387 | 1.0000 | 1.0000 |
| 225470_7325718_1_7325718 | ambient | 0.9052 | 0.9100 | 0.7364 | 0.7839 | 1.0000 | 1.0000 |
| 227512_7333052_1_157675 | ambient | 2.3154 | 1.8143 | 1.5221 | 1.1148 | 1.0000 | 1.0000 |
| 227534_7334641_1_7334641 | ambient | 3.0880 | 2.7810 | 2.1594 | 1.8419 | 1.0000 | 1.0000 |

---

## Worst-Error Samples (Base Model)

### 227534_7334641_1_7334641

**WER:** 3.0880 | **CER:** 2.1594

**Reference (first 300 chars):**
> The patient is being seen for worsening neck pain after a recent auto accident, with symptoms improving initially following previous injuries in January 2026 but now exacerbated. History of Present Illness The patient reports worsening neck and back pain, rating it as 9 out of 10, which started imme

**Base hypothesis (first 300 chars):**
> You filled out our giant online intake AC. So you're seeing me for valuation from this, for injuries from this auto accident, 227, 26. You are left-handed. Yes. And self-employed with Uber? Yes, Uber and Lyft. Uber and Lyft driver. All right, the accident was 227. You were driving, I assume? Yes, so

**LoRA hypothesis (first 300 chars):**
> You filled out our giant online intake AC. So you're seeing me for evaluation from this, for injuries from this auto accident, 227.26. You are left-handed. Yes. And self-employed with Uber? Yes, Uber and Lyft. All right, the accident was 227, you were driving, I assume? Yes. So seat belted, driver. 

### 224938_7286318_1_151007

**WER:** 2.7191 | **CER:** 1.7462

**Reference (first 300 chars):**
> The patient is experiencing bothersome right shoulder, lumbar spine, and right knee symptoms, including pain, with limited mobility and tenderness upon palpation. History of Present Illness The patient is experiencing persistent symptoms of pain in his right shoulder, low back, and right knee, with 

**Base hypothesis (first 300 chars):**
> All right, so you're sending me for follow-up for this work injury from December of 25. Last time I saw you, we continued treatment for your low back, right shoulder, left wrist, left hand, right knee, right ankle, right foot. I ordered some MRI scans of the right shoulder, right knee, and low back.

**LoRA hypothesis (first 300 chars):**
> all right so you're saving me for follow-up for this work injury from december 25 last time i saw you continue treatment for your low back uh right shoulder knee left wrist left hand right knee right ankle right foot i ordered some mri scans of the right shoulder right knee and low back looks like t

### 227512_7333052_1_157675

**WER:** 2.3154 | **CER:** 1.5221

**Reference (first 300 chars):**
> The patient presents with acute muscle metastatic sprain, strain of cervical and thoracic spine, post-traumatic, as well as bilateral shoulder sprains, post-traumatic, resulting in severe pain in their neck, back, and shoulders. History of Present Illness The patient reports experiencing aching, thr

**Base hypothesis (first 300 chars):**
> Hey, Mr. Clark. How are you doing? I'm doing well, sir. I'm Dr. Herman. Nice to meet you. You're doing well. Probably better than you. Yeah, you are. I'm sorry. So let me just pull up your paperwork here. So you see me for injuries from an auto accident, 22526. You're right-handed. You're an assista

**LoRA hypothesis (first 300 chars):**
> hey mr clark how are you doing well from dr hermann nice to meet you well probably better than you yeah you are i'm sorry so let me just pull up your paperwork here all right so you see me for uh for injuries from an auto accident 225 26. you're right-handed you're an assistant supervisor at amports


---

*Generated by eval_asr_quality.py*