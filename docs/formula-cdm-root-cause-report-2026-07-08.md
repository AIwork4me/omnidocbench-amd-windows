# Formula CDM Root-Cause Report

Generated from the repository diagnostics CLI.

## Full-Run Metrics

- Overall notebook: 95.25242128285625
- text_block_Edit_dist: 0.03396970391068958
- display_formula_CDM: 94.83258612806141
- table_TEDS: 94.32164811157631
- reading_order_Edit_dist: 0.12832524445172197

## Hard-Subset Metrics

- Overall notebook: 88.263758235825
- text_block_Edit_dist: 0.1112633604499296
- display_formula_CDM: 75.91761075246795
- table_TEDS: 100.0
- reading_order_Edit_dist: 0.07988543758271256

## Prediction Stats

- Pages: 1651
- Successful pages: 1649
- Failed pages: 2

## Hard-Case Attribution

- evaluator_gt_compat: 17
- pred_latex_unrenderable: 9
- normalization_or_matching: 5
- extraction_or_matching: 7
- model_or_dataset_gap: 3
- pending: 5

## Official Vs Lightweight Hard-Subset Comparison

- lightweight: pages=31 ok=31 fail=0 Formula CDM=75.90153548365073 Overall=88.25782646934708
- official: pages=31 ok=31 fail=0 Formula CDM=80.7229576127384 Overall=89.88305977230102
- Formula CDM delta official-lightweight: 4.8214

## Selected-Case Recovery Potential

- Values are sample-level upper bounds over the selected hard cases, not direct full-run score deltas.
- evaluator_gt_compat: count=17 sample_cdm_gap_upper_bound=17.0000
- pred_latex_unrenderable: count=9 sample_cdm_gap_upper_bound=9.0000
- normalization_or_matching: count=5 sample_cdm_gap_upper_bound=4.5520
- extraction_or_matching: count=7 sample_cdm_gap_upper_bound=7.0000
- model_or_dataset_gap: count=3 sample_cdm_gap_upper_bound=3.0000
- pending: count=5 sample_cdm_gap_upper_bound=0.0000

## Top Cases

- cdm-0001 idx=3 cdm=1.0 edit=0.0 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0002 idx=4 cdm=1.0 edit=0.0 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0003 idx=8 cdm=1.0 edit=0.2635135135135135 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0004 idx=11 cdm=1.0 edit=0.07317073170731707 class=pending reason=control_high_cdm img=page-d1561665-5359-42fe-920c-d6e3bff81953.png
- cdm-0005 idx=1 cdm=1.0 edit=0.0 class=pending reason=control_high_cdm img=page-14cd673f-d86d-45a7-a13e-2b4e1d91c08f.png
- cdm-0006 idx=3 cdm=0.0 edit=0.1293800539083558 class=evaluator_gt_compat reason=cdm_zero img=page-cdd33cf6-76ce-42bb-a99c-342c861afed0.png
- cdm-0007 idx=1 cdm=0.036 edit=0.038135593220338986 class=normalization_or_matching reason=cdm_low_edit_close img=page-7dfc88d8-6d95-446c-b910-2410e8552f76.png
- cdm-0008 idx=1 cdm=0.0 edit=0.6300813008130082 class=evaluator_gt_compat reason=cdm_zero img=page-67013be9-58e5-4842-809d-7a3c1fc91fc7.png
- cdm-0009 idx=1 cdm=0.394 edit=0.0893760539629005 class=normalization_or_matching reason=cdm_low_edit_close img=page-49776237-a9be-441d-a326-002eb7084385.png
- cdm-0010 idx=10 cdm=0.0 edit=0.48502994011976047 class=model_or_dataset_gap reason=cdm_zero img=page-b2349b51-01db-4dc1-9e4a-58e52f5e4362.png
- cdm-0011 idx=16 cdm=0.0 edit=1.0 class=extraction_or_matching reason=prediction_empty img=page-21967f5d-667d-488e-a5b3-76b9d6f53656.png
- cdm-0012 idx=20 cdm=0.0 edit=1.0 class=extraction_or_matching reason=prediction_empty img=page-21967f5d-667d-488e-a5b3-76b9d6f53656.png
- cdm-0013 idx=21 cdm=0.0 edit=1.0 class=extraction_or_matching reason=prediction_empty img=page-21967f5d-667d-488e-a5b3-76b9d6f53656.png
- cdm-0014 idx=4 cdm=0.0 edit=0.1277533039647577 class=pred_latex_unrenderable reason=cdm_zero img=page-cdb92c2f-f43f-45ef-ace7-91d4664a7834.png
- cdm-0015 idx=12 cdm=0.0 edit=0.030303030303030304 class=normalization_or_matching reason=cdm_zero img=page-cdb92c2f-f43f-45ef-ace7-91d4664a7834.png
- cdm-0016 idx=9 cdm=0.0 edit=0.09210526315789473 class=evaluator_gt_compat reason=cdm_zero img=page-e721a819-6dbf-453a-a7ad-857c24f9aa3e.png
- cdm-0017 idx=3 cdm=0.0 edit=0.24104234527687296 class=evaluator_gt_compat reason=cdm_zero img=page-dc728bd5-50a9-41e8-9e5a-d4b01e6664a2.png
- cdm-0018 idx=16 cdm=0.0 edit=0.175 class=evaluator_gt_compat reason=cdm_zero img=page-dc728bd5-50a9-41e8-9e5a-d4b01e6664a2.png
- cdm-0019 idx=18 cdm=0.0 edit=0.05952380952380952 class=evaluator_gt_compat reason=cdm_zero img=page-dc728bd5-50a9-41e8-9e5a-d4b01e6664a2.png
- cdm-0020 idx=4 cdm=0.0 edit=0.47555555555555556 class=evaluator_gt_compat reason=cdm_zero img=page-85377cdf-d6a2-4611-bd50-08795bf7acb6.png

## Recommended Next Action

Official doc_parser is materially higher on this hard subset; prioritize official/lightweight adapter delta analysis before changing public reference scores.
