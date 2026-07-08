# Formula CDM Root-Cause Report

Generated from the repository diagnostics CLI.

## Full-Run Metrics

- Overall notebook: 95.25242128285625
- text_block_Edit_dist: 0.03396970391068958
- display_formula_CDM: 94.83258612806141
- table_TEDS: 94.32164811157631
- reading_order_Edit_dist: 0.12832524445172197

## Official Full-Run Metrics

- Overall notebook: 95.5443384073928
- text_block_Edit_dist: 0.0412925380964843
- display_formula_CDM: 96.68287912322604
- table_TEDS: 94.0793899086008
- reading_order_Edit_dist: 0.12964303689995774
- Formula CDM delta vs lightweight full-run: +1.8503
- Formula CDM delta vs official target 97.49: -0.8071
- Adapter pages: 1651 total, 1650 ok, 1 VLM 500 failure.
- Failed official page: `newspaper_The Times UK_0801@magazinesclubnew_page_031.png`.
- CDM samples: 2352 total, 0 errors, 0 exceptions, 0 timeouts.
- Page matching fallbacks: 2 quick-match timeouts, both recovered by fallback.

## Score Comparison

| Metric | Official baseline | Previous lightweight full-run | Current official full-run | Current vs lightweight | Current vs official |
|---|---:|---:|---:|---:|---:|
| Overall | 96.33 | 95.2524 | 95.5443 | +0.2919 | -0.7857 |
| Text Edit-distance | 0.0330 | 0.03397 | 0.04129 | +0.00732 worse | +0.00829 worse |
| Formula CDM | 97.49 | 94.8326 | 96.6829 | +1.8503 | -0.8071 |
| Table TEDS | 94.76 | 94.3216 | 94.0794 | -0.2423 | -0.6806 |
| Table TEDS-S | 97.11 | 96.6450 | 96.4162 | -0.2288 | -0.6938 |
| Reading-order Edit-distance | 0.1270 | 0.12833 | 0.12964 | +0.00132 worse | +0.00264 worse |

## Formula CDM Root Cause Conclusion

- The original Formula CDM deficit is primarily an adapter/VLM-output-path issue: switching from the lightweight path to the official PaddleOCR `doc_parser` path raises full-set Formula CDM from 94.8326 to 96.6829.
- The remaining gap to the 97.49 official target is not explained by GT self-CDM evaluator compatibility: GT self-CDM failures are now 0, and the official full-set CDM pass had 0 errors, 0 exceptions, and 0 timeouts over 2352 formula samples.
- The remaining deficit is best attributed to model/server/output differences in this Windows AMD llama.cpp GGUF setup, plus one official VLM 500 page and residual malformed prediction LaTeX cases.

## Hard-Subset Metrics

- Overall notebook: 91.72308608818717
- text_block_Edit_dist: 0.11128056075609505
- display_formula_CDM: 86.297314340171
- table_TEDS: 100.0
- reading_order_Edit_dist: 0.07851275398628153

## Prediction Stats

- Pages: 1651
- Successful pages: 1649
- Failed pages: 2

## Hard-Case Attribution

- pred_latex_unrenderable: 6
- normalization_or_matching: 5
- extraction_or_matching: 7
- model_or_dataset_gap: 5
- pending: 23

## Residual Pred Render Evidence

- GT self-CDM compatibility failures after the normalization patch: 0.
- Remaining pred render failures: 6.
- WSL render probe shows all 6 remaining pred render failures enter the CDM path with raw prediction braces already unbalanced; pdflatex then fails with runaway/missing-brace errors.
- Current residual pred render cases are therefore classified as malformed prediction LaTeX rather than an evaluator compatibility bug: `cdm-0023`, `cdm-0028`, `cdm-0031`, `cdm-0041`, `cdm-0042`, `cdm-0046`.
- No broad prediction repair or GT rewrite was applied.

## Official Vs Lightweight Hard-Subset Comparison

- lightweight: pages=31 ok=31 fail=0 Formula CDM=86.297314340171 Overall=91.72308608818717
- official: pages=31 ok=31 fail=0 Formula CDM=90.20197733045369 Overall=93.04273301153945
- Formula CDM delta official-lightweight: 3.9047

## Selected-Case Recovery Potential

- Values are sample-level upper bounds over the selected hard cases, not direct full-run score deltas.
- pred_latex_unrenderable: count=6 sample_cdm_gap_upper_bound=6.0000
- normalization_or_matching: count=5 sample_cdm_gap_upper_bound=4.5520
- extraction_or_matching: count=7 sample_cdm_gap_upper_bound=7.0000
- model_or_dataset_gap: count=5 sample_cdm_gap_upper_bound=5.0000
- pending: count=23 sample_cdm_gap_upper_bound=18.0000

## Top Cases

- cdm-0001 idx=3 cdm=1.0 edit=0.0 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0002 idx=4 cdm=1.0 edit=0.0 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0003 idx=8 cdm=1.0 edit=0.2635135135135135 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0004 idx=11 cdm=1.0 edit=0.07317073170731707 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0005 idx=1 cdm=1.0 edit=0.0 class=pending reason=control_high_cdm img=page-14cd673f-d86d-45a7-a13e-2b4e1d91c08f.png
- cdm-0006 idx=3 cdm=0.0 edit=0.1293800539083558 class=pending reason=cdm_zero img=page-cdd33cf6-76ce-42bb-a99c-342c861afed0.png
- cdm-0007 idx=1 cdm=0.036 edit=0.038135593220338986 class=normalization_or_matching reason=cdm_low_edit_close img=page-7dfc88d8-6d95-446c-b910-2410e8552f76.png
- cdm-0008 idx=1 cdm=0.0 edit=0.6300813008130082 class=pending reason=cdm_zero img=page-67013be9-58e5-4842-809d-7a3c1fc91fc7.png
- cdm-0009 idx=1 cdm=0.394 edit=0.0893760539629005 class=normalization_or_matching reason=cdm_low_edit_close img=page-49776237-a9be-441d-a326-002eb7084385.png
- cdm-0010 idx=10 cdm=0.0 edit=0.48502994011976047 class=pending reason=cdm_zero img=page-b2349b51-01db-4dc1-9e4a-58e52f5e4362.png
- cdm-0011 idx=16 cdm=0.0 edit=1.0 class=extraction_or_matching reason=prediction_empty img=page-21967f5d-667d-488e-a5b3-76b9d6f53656.png
- cdm-0012 idx=20 cdm=0.0 edit=1.0 class=extraction_or_matching reason=prediction_empty img=page-21967f5d-667d-488e-a5b3-76b9d6f53656.png
- cdm-0013 idx=21 cdm=0.0 edit=1.0 class=extraction_or_matching reason=prediction_empty img=page-21967f5d-667d-488e-a5b3-76b9d6f53656.png
- cdm-0014 idx=4 cdm=0.0 edit=0.1277533039647577 class=pending reason=cdm_zero img=page-cdb92c2f-f43f-45ef-ace7-91d4664a7834.png
- cdm-0015 idx=12 cdm=0.0 edit=0.030303030303030304 class=normalization_or_matching reason=cdm_zero img=page-cdb92c2f-f43f-45ef-ace7-91d4664a7834.png
- cdm-0016 idx=9 cdm=0.0 edit=0.09210526315789473 class=pending reason=cdm_zero img=page-e721a819-6dbf-453a-a7ad-857c24f9aa3e.png
- cdm-0017 idx=3 cdm=0.0 edit=0.24104234527687296 class=pending reason=cdm_zero img=page-dc728bd5-50a9-41e8-9e5a-d4b01e6664a2.png
- cdm-0018 idx=16 cdm=0.0 edit=0.175 class=pending reason=cdm_zero img=page-dc728bd5-50a9-41e8-9e5a-d4b01e6664a2.png
- cdm-0019 idx=18 cdm=0.0 edit=0.05952380952380952 class=pending reason=cdm_zero img=page-dc728bd5-50a9-41e8-9e5a-d4b01e6664a2.png
- cdm-0020 idx=4 cdm=0.0 edit=0.47555555555555556 class=pending reason=cdm_zero img=page-85377cdf-d6a2-4611-bd50-08795bf7acb6.png

## Recommended Next Action

Official doc_parser is materially higher on the hard subset and full set, but still lands below the public 97.49 Formula CDM target on this machine/run. Treat the remaining gap as adapter/server/model-output delta evidence, not an evaluator GT self-CDM bug: scorer self-checks are clean and full-set CDM had no errors, exceptions, or timeouts.
