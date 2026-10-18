# Korean → English conversational fine-tuning

Research checked 2026-10-18. No dataset downloaded or training started.

## Candidate data

- **AI Hub: Daily-life and colloquial Korean-English parallel translation corpus**: daily-life and colloquial parallel translations, a close match for conversational adaptation. [Dataset 71265](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=71265). The older Korean–English corpus also includes 400,000 colloquial and 100,000 dialogue sentences ([official package description](https://www.aihub.or.kr/aihubdata/data/view.do?aihubDataSe=dataPckage&currMenu=511&dataPckageSn=4&topMenu=100)). [AI Hub policy](https://aihub.or.kr/intrcn/guid/usagepolicy.do?currMenu=151&topMenu=105) requires a separate agreement for individuals or organizations located outside Korea; do not assume a third-party mirror removes this restriction.
- **OPUS OpenSubtitles, Korean–English**: film/TV subtitle pairs are a useful candidate for short, emotional dialogue. [Corpus and download links](https://opus.nlpl.eu/legacy/OpenSubtitles-v2018.php). Filter alignment errors, duplicate versions, credits and subtitle markup. The page requests attribution; it is not sufficient evidence of blanket commercial rights to the underlying subtitles. Verify the intended use before selecting it for a released product.
- **Tatoeba, Korean–English linked sentences**: useful supplementary short sentences, not a coherent dialogue corpus. [Downloads](https://tatoeba.org/en/downloads), [reuse guide](https://en.wiki.tatoeba.org/articles/show/using-the-tatoeba-corpus). Text defaults to CC BY 2.0 FR; retain sentence IDs and author attribution. Select actual linked translations, never pair unrelated rows.
- **Human-reviewed dialogue from material we are allowed to use**: best fit for webtoon names, omitted subjects, honorifics, slang and emotional tone. Correct OCR before making the reference translation. Keep source provenance and usage permission with every example.

## Suggested first experiment (not a proven optimal recipe)

1. Build 300–500 held-out, human-reviewed examples from separate episodes or works, including ordinary dialogue, slang, names and honorifics. Keep this set out of training and model selection.
2. Start with 5,000–20,000 clean permitted parallel pairs rather than all available data. Review a random sample for meaning and natural English, and remove duplicate/near-duplicate pairs before splitting.
3. Split by work/episode/movie, not random subtitle lines, to prevent related dialogue leaking between training, validation and test sets.
4. Train a small LoRA baseline and compare with unchanged M2M100. Judge meaning, naturalness, speaker relationships and name consistency with a bilingual reviewer; use automatic scores only as supporting measurements.
5. Evaluate both clean-text translation and the full OCR pipeline separately. Fine-tuning the translator does not repair missing text or incorrect OCR by itself.

Keep source text, corrected English, source ID, work/episode ID and license/provenance. Do not use the current model's unreviewed translations as gold labels. The current translator takes text segments independently; conversational history requires matching training and inference changes, not simply adding unused context fields to the dataset.
