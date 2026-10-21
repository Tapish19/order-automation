# NaturaX requirements checklist

Paths are relative to this project. Frontend screens live in `frontend/src/App.tsx`; all API handlers live in `backend/app/main.py` unless another path is named. Executed pass/fail evidence is in `TEST_RESULTS.md` and the machine-readable files under `artifacts/`. A code mapping is not, by itself, a claim of execution.

## 1. Exact CSV / Excel compatibility

| Requirement | Exact implementation | Verification |
|---|---|---|
| Exactly ten specified fields, no extra columns needed | `backend/app/validation.py:HEADERS`, `read_file`; `POST /api/uploads`; Upload orders screen; both main files in `samples/` | `backend/tests/test_imports.py:test_exact_ten_headers_csv_and_blank_dispatch`, `test_exact_ten_headers_excel`; browser CSV/Excel flows |
| Optional confirmed_at / delivery_attempt_at | `validation.py:OPTIONAL`, `normalize_date` call; nullable columns in `models.py:Order`; `rules.py:detect` | `test_rules.py:test_confirmation_timestamp_overrides_old_order_date`, `test_failed_delivery_optional_attempt_is_immediate` |
| Blank dispatch valid for unshipped orders | `validation.py:validate`, status-specific `required` checks | Exact-ten-header CSV test; configured confirmed-18h challenge B |
| Known confirmation time preferred; order-time fallback if sufficient | `rules.py:detect`, confirmed branch; `validation.py:validate` hourly precision check | Dispatch-boundary tests and confirmation override test |
| Assumption/limitation explicit; no invented timestamps | README → Status-dependent validation and time assumptions; `timeutils.py:normalize_date`; XLSX precision handling in `validation.py:read_file` | `test_imports.py:test_date_only_excel_style_not_invented_as_midnight`; date-only hourly invalid case |

## 2. Five exact rules

| Requirement | Exact implementation | Verification |
|---|---|---|
| Unconfirmed **>2h**, excludes exactly 2h | `rules.py:detect`, strict timedelta comparison | `test_rules.py:test_unconfirmed_strict_boundary` (below/exact/above) |
| Confirmed, not dispatched within 24h | `rules.py:detect`, `>=dispatch_hours`; unshipped consistency in validator | `test_dispatch_boundary_and_fallback` (below/exact/above) |
| Dispatched, past expected, undelivered | `rules.py:SHIPPED`, `detect`; `timeutils.py:past_expected` | `test_expected_timestamp_strict_boundary` |
| Failed attempt immediate follow-up | `rules.py:detect`, urgent priority, deadline=now; priority desk sorts urgent then earliest deadline in `GET /api/dashboard` | `test_failed_delivery_optional_attempt_is_immediate`, `test_priority_desk_places_immediate_failures_first` |
| Value **>₹5,000**, still undelivered past expected | `models.py:Order.value_paise`; `rules.py:detect`, strict paise comparison | `test_high_value_strict_boundary` (4999.99 / 5000 / 5000.01) |
| Delivered orders excluded | `rules.py:TERMINAL` early return | `test_terminal_orders_do_not_trigger_undelivered_rules` |
| Missing/invalid prerequisites become correction issues | `validation.py:validate`; `services.py:import_records`, `reconcile`; `models.py:DataIssue` | Parametrized invalid-row tests, `test_rule_change_may_require_missing_expected_date`, chronology test |
| Consistent Asia/Kolkata and date-only expected interpretation | `timeutils.py:IST`, `normalize_date`, `expected_boundary`, `day_bounds`; `frontend/src/api.ts:when` | IST date-only end-of-day and naive-offset tests; README policy |

## 3. Data-validation workflow

| Requirement | Exact implementation | Verification |
|---|---|---|
| Dedicated correction screen | App → **Data corrections**; `GET /api/data-issues` (open/resolved/all) | Browser challenge A |
| Filename, row, ID, bad field, explanation, recommended correction | `models.py:DataIssue`; `services.py:add_issue`; correction table | Invalid-row tests verify filename/source row and recommendations |
| Correct a record, not merely hide its error | **Correct row** dialog; `POST /api/data-issues/{issue_id}/correct`; row revalidated and audited | `test_correction_screen_api_imports_and_resolves_source_row`, `test_missing_id_can_be_corrected`, invalid-correction test; browser correction |
| Duplicates within file | `services.py:import_records`, ID grouping + signature comparison | `test_identical_and_conflicting_duplicates_in_one_file` |
| Duplicates against prior imports vs legitimate updates | `services.py:import_records`, identity comparison and change diff | `test_existing_identity_collision_rejected_but_status_update_allowed` |
| Valid rows import despite bad rows | Per-row validation loop in `services.py:import_records`; one readable batch transaction | `test_interview_A_deliberately_invalid_file`, parametrized invalid-row tests |
| Rejected newer snapshots do not create false exceptions from stale order data | `services.py:reconcile` pauses orders with unresolved import errors; last valid record and tasks retained | `test_rejected_update_pauses_new_exceptions_until_source_is_corrected` |
| Unreadable file clearly rejected | `validation.py:read_file`, `FileError`; `POST /api/uploads` errors and size limits | `test_unreadable_files_fail_without_importing`, duplicate-header test |

## 4. Exception and task lifecycle

| Requirement | Exact implementation | Verification |
|---|---|---|
| Every exception includes customer/reason/priority/employee/action/deadline/status | `models.py:Task` + `Order`; `services.py:task_dict`; `/api/tasks` and Manage task dialog | Failed-delivery detail assertions, browser task dialog |
| Each exception creates a persistent follow-up task | `services.py:reconcile`; `models.py:Task`; SQLite `data/naturax.db` | Sample category test, restart persistence test |
| Idempotent uploads / evaluation, no duplicate active tasks | Partial unique index `models.py:Task.__table_args__`; `reconcile` active-episode map; mutation lock | `test_interview_C_repeated_uploads_and_evaluations`, concurrent-reupload test; browser C compares task IDs |
| Preserve assignment and history on reimport | `services.py:import_records` updates Order separately; `reconcile` retains Task owner, deadline, detection and status | `test_interview_D_E_overdue_reassignment_persistence_and_audit`; browser D |
| Define updated/resolved/recurrent behavior | README → Task and exception lifecycle; `services.py:reconcile`; `PATCH /api/tasks/{task_id}` | `test_resolve_same_problem_no_reopen_then_new_episode`, business-resolution/history test |
| Manager can change status and reassign overdue work | Follow-up tasks → Manage; `PATCH /api/tasks/{task_id}` | Browser D; employee assignment test; backend D/E |
| Audit every assignment/reassignment/status change | `services.py:audit`, `reconcile`; `main.py:update_task`; `models.py:Audit` | Reassignment user/timestamp/details assertions; browser E |
| Audit has order ID, responsible user, action, timestamp, details | `models.py:Audit`; `X-User` dependency; **Audit trail**, `GET /api/audit?order_id=...&action=...` | Backend/browser D/E; README identifies local named-user limitation |

## 5. Dashboard and reporting precision

| Requirement | Exact screen / endpoint / file | Verification |
|---|---|---|
| Total orders uploaded | Dashboard → Rows uploaded plus unique accepted order count; `GET /api/dashboard` keys `uploaded_rows`, `unique_orders_all_time`, `unique_orders` | Reupload test asserts 4 source rows / 1 unique order; browser C asserts 441 source rows |
| Orders requiring attention | Dashboard card; `orders_requiring_attention` counts unique IDs with unresolved matching tasks | Backend filter test; browser dashboard |
| Open tasks | Card: open + in_progress; `open_tasks`; task filter `status=pending` | `test_pending_filter_includes_in_progress_and_excludes_resolved` |
| Overdue tasks | Card and overdue-only queue; task_dict compares deadline/current time for unresolved tasks | Failed delivery immediate/deadline test; overdue reassignment scenario |
| Exceptions grouped by category | Recharts category BarChart; `exceptions_by_category` | Backend sample covers all five; browser CSV/category test |
| Employee-wise pending tasks | Team workload; `employee_pending`; task-owner filtering | Backend filtered employee count; browser filters/reassignment |
| Immediate high-priority cases | Priority desk and Manage dialog; `immediate_cases` sorted urgent then deadline | Priority ordering test; browser failed-delivery handover |
| Date/type/employee/priority filters work on actual API results | Shared filter toolbar; `main.py:select_records`, query parameters on dashboard/tasks/orders | `test_filters_change_backend_results`; browser B captures actual filtered response |
| Explain source rows vs unique orders | Dashboard labels, Upload history, README → Validation and duplicate workflow | Backend/browser repeat-file assertions |
| Daily downloadable CSV: new/unresolved/overdue/high priority/employee actions | **Daily reports**; `GET /api/reports/daily.csv?report_date=...`; named sections | `test_report_all_sections_and_new_definition_ist`; browser downloads real CSV |
| New = first detected on selected date, persisted time | `models.py:Task.first_detected_at`; `services.py:reconcile`; report IST `[start,end)` comparison | Daily-report test includes prior-day unresolved and selected-day resolved exceptions |

## 6. Business impact demonstration

| Question | Exact documentation |
|---|---|
| How manual work is reduced | README → Business impact, question 1; DEMO_SCRIPT 0:00–0:45 |
| How forgotten orders are prevented | README → Business impact, question 2; persistence/task lifecycle |
| KPIs proving effectiveness | README → Business impact, question 3; current count KPIs distinguished from derivable duration/outcome KPIs |
| Daily time savings and numeric example with assumptions | README → Business impact, question 4: 340m baseline, 35m automated admin, estimated 305m savings; DEMO_SCRIPT final 25 seconds |
| Remaining limitations | README → Business impact, question 5 and time/identity/report policies; DEMO_SCRIPT closing |

## 7. Samples and acceptance challenges

| Requirement / challenge | Implementation / demonstration | Automated evidence |
|---|---|---|
| >=100 realistic orders; clean + five categories + duplicate/missing/invalid | `sample_data.py:make_records`, `generate_samples`; 147 rows in `samples/naturax_orders.csv` and `.xlsx` | `test_sample_has_100_plus_all_rules_and_bad_rows` |
| Threshold-adjacent records | `EDGE-*` IDs in sample files; `samples/manifest.json` reference clock | Parametrized 2h / 24h / expected timestamp / INR boundaries; challenge B at 18h |
| No external production integrations required | Empty SQLite + seeded employees/rules + local file uploads; no credentials or integration configuration | All tests run without Shopify/WhatsApp/courier/NaturaX access |
| A: invalid dataset error detection | `samples/interview_invalid.csv`; Upload orders → Data corrections → Correct row | Backend `test_interview_A_deliberately_invalid_file`; browser A |
| B: change dispatch 24h → 12h | Business rules → Save & reevaluate; `/api/rules` PUT; stored confirmed-18h cases | Backend `test_interview_B_threshold_24_to_12`; browser B compares count before/after |
| C: repeat same file, no duplicate tasks | Upload orders repeatedly; unchanged import result; `/api/tasks` stable IDs | Backend C + concurrent test; browser C uploads main file three times |
| D: overdue task reassignment persists | Follow-up tasks → Failed delivery / Overdue → Manage; reupload and refresh | Backend D/E also opens a fresh app/engine against same SQLite file; browser D |
| E: reassignment audit with user/time | Audit trail → Order ID + task_reassigned | Backend and browser D/E inspect exact responsible user, timestamp, old/new owner and overdue flag |

## 8. Final submission

| Deliverable | Location |
|---|---|
| Functional application / local demonstration | `start.ps1` / `start.sh`; built frontend served by FastAPI on http://127.0.0.1:8000; `DEMO_SCRIPT.md` |
| Complete frontend and backend source | `frontend/src/`, `frontend/vite.config.ts`, `backend/app/` |
| CSV and Excel sample >=100 orders | `samples/naturax_orders.csv`, `samples/naturax_orders.xlsx` (147 each) |
| Exact setup instructions | `README.md`; pinned `requirements.lock.txt` and `frontend/package-lock.json` |
| Configurable business rules | Business rules screen; `GET/PUT /api/rules`; `models.py:RuleConfig` |
| Automatic periodic detection | `main.py:create_app` / `ticker`; `backend/tests/test_scheduler.py` advances the clock and proves a task appears without any evaluate/upload action |
| Persistent database and audit | `database.py`, `models.py`; default `data/naturax.db`; Audit trail screen |
| Five-minute demonstration | `DEMO_SCRIPT.md`, including all A–E challenges and impact explanation |
| Automated test source and actual results | `backend/tests/`, `frontend/e2e/interview.spec.ts`, `TEST_RESULTS.md`, `artifacts/pytest-results.xml`, `artifacts/browser-results.json` |
| Requirement-to-implementation mapping | This file |
| Practical scope, no unnecessary integrations | Local CSV/Excel import, SQLite persistence, manual real-world follow-up; limitations explicit in README |
