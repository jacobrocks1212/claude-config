# Calibration Report

**Date:** 2026-05-06
**Mode:** Dry run — Full bulk
**PRs analyzed:** 9 (17643, 17821, 17942, 18244, 18248, 18276, 18286, 18309, 18377)
**Total plugin findings analyzed:** 82
**Total human comments analyzed:** 0

## Per-Category Results

| Category | TP | FP | FN | Old Multiplier | New Multiplier |
|----------|----|----|-----|----------------|----------------|
| api_design | 0 | 0 | 0 | 1.0000 | 1.0000 |
| architecture | 0 | 7 | 0 | 1.0000 | 0.7500 |
| blocking | 0 | 2 | 0 | 1.0000 | 0.7500 |
| cognito-api-design | 0 | 3 | 0 | 1.0000 | 0.7500 |
| cognito-api-design, cognito-consistency | 0 | 1 | 0 | 1.0000 | 0.7500 |
| cognito-architecture | 0 | 15 | 0 | 1.0000 | 0.7500 |
| cognito-architecture, cognito-api-design | 0 | 1 | 0 | 1.0000 | 0.7500 |
| cognito-architecture, cognito-api-design, cognito-consistency | 0 | 1 | 0 | 1.0000 | 0.7500 |
| cognito-consistency | 0 | 1 | 0 | 1.0000 | 0.7500 |
| cognito-consistency-checker | 0 | 3 | 0 | 1.0000 | 0.7500 |
| cognito-frontend | 0 | 16 | 0 | 1.0000 | 0.7500 |
| cognito-test-coverage | 0 | 4 | 0 | 1.0000 | 0.7500 |
| consistency | 0 | 7 | 0 | 0.8000 | 0.6000 |
| critical | 0 | 1 | 0 | 1.0000 | 0.7500 |
| frontend | 0 | 9 | 0 | 1.0000 | 0.7500 |
| performance | 0 | 0 | 0 | 0.9000 | 0.9000 |
| security | 0 | 1 | 0 | 1.2000 | 0.9000 |
| template_binding | 0 | 0 | 0 | 0.7000 | 0.7000 |
| test-coverage | 0 | 7 | 0 | 1.0000 | 0.7500 |
| test-quality | 0 | 3 | 0 | 1.0000 | 0.7500 |
| testing | 0 | 0 | 0 | 0.9000 | 0.9000 |

## Proximity Match Details

| PR | Finding File:Line | Comment File:Line | Match |
|----|-------------------|-------------------|-------|
| 17821 | cognito.services/controllers/svccontrollers/cognitopaysettings/cognitopaypaymentcontroller.cs:44 | — | ✗ |
| 17821 | cognito.core/cognitopay/cognitopayfiltercriteria.cs:6 | — | ✗ |
| 17942 | createpersonformdialog.vue:2 | — | ✗ |
| 17942 | createpersonformdialog.vue:46 | — | ✗ |
| 17942 | createpersonformdialog.vue:42 | — | ✗ |
| 17942 | systemtemplateservice.cs:39 | — | ✗ |
| 17942 | systemtemplateservice.cs:79 | — | ✗ |
| 17942 | systemtemplateservice.cs:71 | — | ✗ |
| 17942 | selectpaymentaccount.vue:6 | — | ✗ |
| 17942 | newbuttonmenu.vue:88 | — | ✗ |
| 17942 | systemtemplateservice.cs:102 | — | ✗ |
| 17942 | createpersonformdialog.vue:130 | — | ✗ |
| 17942 | selectablecardgroup.vue:59 | — | ✗ |
| 17942 | selectablecardgroup.vue:64 | — | ✗ |
| 17942 | selectpaymentaccount.vue:160 | — | ✗ |
| 17942 | newbuttonmenu.vue:93 | — | ✗ |
| 18244 | cognito.services/controllers/svccontrollers/form/formsadmincontroller.cs:1487 | — | ✗ |
| 18244 | cognito.core/indexrepository.cs:944 | — | ✗ |
| 18244 | cognito.services/controllers/svccontrollers/form/formsadmincontroller.cs:1489 | — | ✗ |
| 18244 | cognito.core/services/taskreminderservice.cs:78 | — | ✗ |
| 18244 | cognito.core/indexrepository.cs:944 | — | ✗ |
| 18244 | cognito.core/services/taskreminderservice.cs:76 | — | ✗ |
| 18244 | cognito.services/controllers/svccontrollers/form/formsadmincontroller.cs:1489 | — | ✗ |
| 18248 | cognito.core/services/forms/personsubmissionservice.cs:113 | — | ✗ |
| 18248 | cognito.core/services/forms/personsubmissionservice.cs:110 | — | ✗ |
| 18248 | cognito.core/services/forms/personsubmissionservice.cs:110 | — | ✗ |
| 18248 | cognito.web.client/apps/spa/src/views/admin/cognito-pay/utils/cognito-pay-utils.ts:19 | — | ✗ |
| 18248 | cognito.web.client/apps/spa/src/components/form-controls/dropdownfilter.vue:647 | — | ✗ |
| 18248 | cognito.web.client/apps/spa/src/components/form-controls/dropdownfilter.vue:449 | — | ✗ |
| 18248 | cognito.web.client/apps/spa/src/views/admin/cognito-pay/cognitopayanalytics.vue:282 | — | ✗ |
| 18248 | cognito.core/services/payment/paymenttransactionservice.cs:253 | — | ✗ |
| 18248 | cognito.services/controllers/svccontrollers/form/personsubmissioncontroller.cs:81 | — | ✗ |
| 18248 | cognito.core/services/forms/personsubmissionservice.cs:49 | — | ✗ |
| 18248 | cognito.core/services/forms/personsubmissionservice.cs:110 | — | ✗ |
| 18248 | cognito.core/services/payment/cognitopayanalyticsservice.cs:424 | — | ✗ |
| 18248 | cognito.core/services/payment/paymenttransactionservice.cs:1116 | — | ✗ |
| 18248 | cognito.web.client/apps/spa/src/views/admin/cognito-pay/utils/cognito-pay-utils.ts:24 | — | ✗ |
| 18276 | cognito.core/services/forms/entryindexservice.cs:3962 | — | ✗ |
| 18276 | cognito.core/services/forms/entryindexservice.cs:3188 | — | ✗ |
| 18276 | cognito.core/services/forms/entryindexservice.cs:4525 | — | ✗ |
| 18276 | cognito.web.client/apps/spa/src/components/form-controls/dropdownfilter.vue:100 | — | ✗ |
| 18276 | cognito.web.client/apps/spa/src/components/table/tablecomponent.vue:134 | — | ✗ |
| 18276 | cognito.web.client/apps/spa/src/views/entries/entrydetailssubmissions.vue:159 | — | ✗ |
| 18286 | cognito.core/services/forms/formsservice.cs:4609 | — | ✗ |
| 18286 | cognito.web.client/apps/spa/src/views/build/identifysubmittersettings.vue:146 | — | ✗ |
| 18286 | cognito.core/model/forms/formentry.cs:80 | — | ✗ |
| 18286 | cognito.web.client/apps/spa/src/views/build/identifysubmittersettings.unit.ts:429 | — | ✗ |
| 18286 | cognito.web.client/apps/spa/src/views/build/identifysubmittersettings.unit.ts:104 | — | ✗ |
| 18286 | cognito.unittests/servicetests/formsservice/submitterpersonsettingstests.cs:185 | — | ✗ |
| 18309 | billing-field-settings.ts:7 | — | ✗ |
| 18309 | form.ts:57 | — | ✗ |
| 18309 | formvalidator.cs:574 | — | ✗ |
| 18309 | formdefinitionconverter.cs:134 | — | ✗ |
| 18309 | form.movebillingfieldsettings.cs:23 | — | ✗ |
| 18309 | billingfieldsettings.cs:14 | — | ✗ |
| 18377 | cognito.core/services/forms/entryindexservice.cs:3175 | — | ✗ |
| 18377 | cognito.core/services/forms/entryindexservice.cs:2147 | — | ✗ |
| 18377 | cognito.web.client/apps/spa/src/components/table/tablecomponent.vue:77 | — | ✗ |
| 18377 | cognito.core/model/forms/form.cs:428 | — | ✗ |
| 18377 | cognito.core/services/payment/ordertransactionservice.cs:62 | — | ✗ |
| 18377 | cognito.web.client/apps/spa/src/components/table/tablecomponent.vue:128 | — | ✗ |
| 18377 | cognito.core/services/payment/ordertransactionservice.cs:256 | — | ✗ |
| 18377 | cognito.core/services/forms/entryindexservice.cs:2147 | — | ✗ |
| 18377 | cognito.web.client/apps/spa/src/components/table/tablecomponent.vue:319 | — | ✗ |
| 18377 | cognito.core/services/forms/entryindexservice.cs:74 | — | ✗ |
| 18377 | cognito.unittests/unit/formtests.cs:214 | — | ✗ |

## False Negative Patterns

Human reviewer comments that the plugin missed:

_(None — all human comments were matched by plugin findings)_

## Dry Run Notice

This was a dry run. No changes were written to `weights.yaml`. Re-run without `--dry-run` to apply EMA updates.
