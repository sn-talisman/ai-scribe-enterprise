# Batch Report — Pipeline v8

**Model:** qwen2.5:14b  
**Samples:** 61 (48 dictation, 13 ambient)  
**Total time:** 818s  
**Avg per sample:** 13.4s  
**Avg keyword overlap:** 34%  

---

## Per-Sample Results

| Sample | Physician | Mode | Audio | Duration | ASR ms | LLM ms | ASR conf | Note conf | PP | Overlap | Status |
|--------|-----------|------|-------|----------|--------|--------|----------|-----------|----|---------|--------|
| antamar_corprew_225470_20260303 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 73.9s | 0 | 73913 | 0.59 | 1.00 | 13 | 36% | ✓ |
| carneater_mull_211802_20260303 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 12.3s | 0 | 12261 | 0.63 | 1.00 | 38 | 32% | ✓ |
| daisy_colina_206551_20260303 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 17.5s | 0 | 17449 | 0.63 | 0.80 | 56 | 40% | ✓ |
| derrick_clarke_227512_20260303 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 13.3s | 0 | 13335 | 0.60 | 1.00 | 49 | 32% | ✓ |
| dexter_colina_206553_20260303 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 14.4s | 0 | 14350 | 0.67 | 0.80 | 22 | 24% | ✓ |
| james_dotson_224938_20260224 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 16.8s | 0 | 16801 | 0.65 | 1.00 | 58 | 26% | ✓ |
| javier_waters_227534_20260303 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 17.2s | 0 | 17192 | 0.63 | 1.00 | 83 | 36% | ✓ |
| maryann_duckett_40761_20260310 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 21.6s | 0 | 21590 | 0.66 | 1.00 | 42 | 38% | ✓ |
| tanya_queen_223818_20260224 | dr_faraz_rahman | ambient | conversation_audio.mp3 | 13.1s | 0 | 13136 | 0.63 | 0.80 | 23 | 42% | ✓ |
| bernadeen_hoard_195713_20260218 | dr_mohammed_alwahaidy | ambient | conversation_audio.mp3 | 14.9s | 0 | 14882 | 0.16 | 1.00 | 220 | 26% | ✓ |
| enzo_blanks_215617_20260218 | dr_mohammed_alwahaidy | ambient | conversation_audio.mp3 | 17.5s | 0 | 17501 | 0.10 | 0.85 | 0 | 18% | ✓ |
| james_quansah_206723_20260218 | dr_mohammed_alwahaidy | ambient | conversation_audio.mp3 | 14.1s | 0 | 14076 | 0.73 | 1.00 | 7 | 32% | ✓ |
| karen_szeliga_226172_20260202 | dr_mohammed_alwahaidy | ambient | conversation_audio.mp3 | 8.3s | 0 | 8283 | 0.64 | 1.00 | 13 | 30% | ✓ |
| adarius_waldon_227038_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 9.2s | 0 | 9222 | 0.64 | 1.00 | 22 | 52% | ✓ |
| anthony_frye_226186_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 19.2s | 0 | 19244 | 0.70 | 0.80 | 72 | 44% | ✓ |
| jamal_rickenbacker_157523_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 11.4s | 0 | 11444 | 0.67 | 1.00 | 25 | 46% | ✓ |
| jeryll_chandler_179713_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 12.3s | 0 | 12297 | 0.66 | 1.00 | 31 | 46% | ✓ |
| marcus_gross_217762_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 10.1s | 0 | 10046 | 0.60 | 1.00 | 16 | 42% | ✓ |
| noel_mcneil_219829_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 12.8s | 0 | 12765 | 0.70 | 1.00 | 57 | 30% | ✓ |
| toni_ferguson johnson_226143_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 10.9s | 0 | 10891 | 0.55 | 1.00 | 39 | 42% | ✓ |
| vaizon_dowdell_222867_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 14.9s | 0 | 14921 | 0.66 | 1.00 | 58 | 50% | ✓ |
| valonte_harrell_226546_20260218 | dr_caleb_ademiloye | dictation | dictation.mp3 | 10.9s | 0 | 10945 | 0.58 | 1.00 | 37 | 26% | ✓ |
| charlene_brandon_225981_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 9.4s | 0 | 9399 | 0.53 | 1.00 | 26 | 38% | ✓ |
| david_augustyniak_226974_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 9.7s | 0 | 9671 | 0.44 | 1.00 | 20 | 18% | ✓ |
| derrick_johnson_226537_20260217 | dr_faraz_rahman | dictation | dictation.mp3 | 20.4s | 0 | 20407 | 0.60 | 1.00 | 61 | 42% | ✓ |
| elizabeth_mcquay_226748_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 20.4s | 0 | 20397 | 0.61 | 1.00 | 54 | 46% | ✓ |
| ericha_gramblin_227093_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 13.9s | 0 | 13860 | 0.45 | 1.00 | 28 | 30% | ✓ |
| kyon_christian_225572_20260303 | dr_faraz_rahman | dictation | dictation.mp3 | 8.7s | 0 | 8745 | 0.53 | 1.00 | 21 | 50% | ✓ |
| malissa_tyson_226806_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 9.5s | 0 | 9495 | 0.51 | 1.00 | 28 | 42% | ✓ |
| miracle_barnes_225835_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 9.1s | 0 | 9054 | 0.50 | 1.00 | 30 | 28% | ✓ |
| riley_dew_226680_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 11.9s | 0 | 11932 | 0.56 | 1.00 | 31 | 22% | ✓ |
| shatia_stowers_224889_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 8.7s | 0 | 8681 | 0.50 | 1.00 | 19 | 40% | ✓ |
| sherwin_maggay_226542_20260219 | dr_faraz_rahman | dictation | dictation.mp3 | 9.1s | 0 | 9106 | 0.49 | 1.00 | 15 | 42% | ✓ |
| breana_ashley_223552_20260202 | dr_mark_reischer | dictation | dictation.mp3 | 8.4s | 0 | 8406 | 0.63 | 1.00 | 13 | 36% | ✓ |
| cameron_schnaack_224632_20260202 | dr_mark_reischer | dictation | dictation.mp3 | 7.5s | 0 | 7545 | 0.64 | 1.00 | 2 | 34% | ✓ |
| emery_phillips_225462_20260202 | dr_mark_reischer | dictation | dictation.mp3 | 7.2s | 0 | 7158 | 0.56 | 1.00 | 8 | 30% | ✓ |
| jody_givler_208349_20260202 | dr_mark_reischer | dictation | dictation.mp3 | 10.3s | 0 | 10329 | 0.64 | 1.00 | 9 | 38% | ✓ |
| vanessa_lewis_225461_20260202 | dr_mark_reischer | dictation | dictation.mp3 | 8.7s | 0 | 8663 | 0.55 | 1.00 | 7 | 34% | ✓ |
| arsenio_birden_50408_20260202 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 8.5s | 0 | 8453 | 0.64 | 1.00 | 13 | 32% | ✓ |
| benjamin_pritchett_216913_20260216 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 9.4s | 0 | 9436 | 0.79 | 1.00 | 21 | 52% | ✓ |
| billie_odell_214110_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 20.9s | 0 | 20928 | 0.04 | 0.85 | 0 | 18% | ✓ |
| christopher_woodward_215454_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 12.0s | 0 | 12028 | 0.69 | 1.00 | 26 | 36% | ✓ |
| daniel_jones_225106_20260303 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 8.6s | 0 | 8624 | 0.75 | 1.00 | 37 | 32% | ✓ |
| devin_martin_216668_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 12.9s | 0 | 12852 | 0.71 | 1.00 | 55 | 42% | ✓ |
| ethel_montalvan_219879_20260224 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 14.8s | 0 | 14793 | 0.49 | 1.00 | 1 | 14% | ✓ |
| fatima_macias_219442_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 10.0s | 0 | 9995 | 0.54 | 1.00 | 13 | 24% | ✓ |
| gianna_monaldi_226762_20260216 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 11.6s | 0 | 11586 | 0.69 | 1.00 | 26 | 30% | ✓ |
| greg_ramsey_217858_20260223 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 12.8s | 0 | 12779 | 0.49 | 1.00 | 2 | 20% | ✓ |
| gwyneth_codd_221985_20260202 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 9.4s | 0 | 9407 | 0.23 | 1.00 | 15 | 10% | ✓ |
| hanna_isper_221568_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 12.3s | 0 | 12338 | 0.75 | 1.00 | 37 | 54% | ✓ |
| jeannette_rufus_216661_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 14.5s | 0 | 14486 | 0.49 | 1.00 | 1 | 14% | ✓ |
| joseph_hunt_203962_20260310 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 13.2s | 0 | 13206 | 0.69 | 1.00 | 26 | 40% | ✓ |
| kelly_holt_219270_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 8.6s | 0 | 8554 | 0.79 | 1.00 | 21 | 30% | ✓ |
| lee_jamison jr_223494_20260216 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 10.2s | 0 | 10157 | 0.67 | 1.00 | 8 | 20% | ✓ |
| sharon_cohen_217541_20260218 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 12.4s | 0 | 12389 | 0.67 | 1.00 | 8 | 46% | ✓ |
| timothy_clark_226530_20260302 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 9.7s | 0 | 9654 | 0.54 | 1.00 | 13 | 36% | ✓ |
| yohannes_woldemariam_214446_20260223 | dr_mohammed_alwahaidy | dictation | dictation.mp3 | 13.6s | 0 | 13576 | 0.58 | 1.00 | 10 | 30% | ✓ |
| andre_owen_225772_20260205 | dr_paul_peace | dictation | dictation.mp3 | 15.4s | 0 | 15392 | 0.52 | 1.00 | 15 | 38% | ✓ |
| april_hicks_226043_20260205 | dr_paul_peace | dictation | dictation.mp3 | 14.5s | 0 | 14453 | 0.53 | 1.00 | 24 | 40% | ✓ |
| muhammad_khan_206270_20260205 | dr_paul_peace | dictation | dictation.mp3 | 12.3s | 0 | 12343 | 0.48 | 1.00 | 27 | 36% | ✓ |
| tonya_dorsey_223752_20260205 | dr_paul_peace | dictation | dictation.mp3 | 10.6s | 0 | 10609 | 0.52 | 1.00 | 28 | 30% | ✓ |

---

## Averages

| Metric | All | Dictation | Ambient |
|--------|-----|-----------|---------|
| Elapsed | 13.41 | 11.73 | 19.60 |
| ASR conf | 0.58 | 0.58 | 0.56 |
| Note conf | 0.98 | 0.99 | 0.94 |
| PP corrections | 29.18 | 24.08 | 48.00 |
| Keyword overlap | 34% | 35% | 32% |
| Errors | 0/61 | 0/48 | 0/13 |

---

## Notes

- Keyword overlap measures domain-relevant word matches between generated and gold notes
- Ambient mode uses diarization (pyannote); dictation mode is single-speaker
- Data source: ai-scribe-data/  (physician-organized encounters)

*Generated by AI Scribe batch_eval.py — version v8*
