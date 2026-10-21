# Five-minute live interview

Before the interview: follow README setup, generate samples once for today, then launch using a new SQLite filename (e.g. `sqlite:///data/interview-2026-10-21.db`). Open http://127.0.0.1:8000 and set **Responsible user** to your name. Keep `samples/naturax_orders.csv` unchanged through the repeat-upload challenge. The API Swagger screen at `/docs` is a useful backup for inspecting JSON.

**Hosted option:** open **https://naturax-order-automation.vercel.app** without starting a local server. The live demo was reset to an empty starting state at the user's request on 21 October 2026, with default rules and four employees. Previous records and audits were backed up locally. Use **Upload orders → Import sample orders** or download the matching files from that screen, including `interview_invalid.csv` and `order_update_delivered.csv`. For a hosted demonstration, use those downloaded files wherever the steps below mention `samples/...`. Download fresh copies after a demo reset: the sample timestamps are refreshed together. Mixing previously downloaded or repository files with the new samples may correctly trigger identity-collision validation. The dispatch threshold starts at 24 hours. The local fresh-database setup above remains available for a separate demonstration.

## 0:00–0:45 — Upload, rules and business value

Explain: “This app turns one CSV/Excel upload into a persistent follow-up queue. The database, rules and reports are local; no production credentials are needed.”

Open **Upload orders → Import sample orders**. Show the 147-row result: new orders, rejected rows, duplicates and generated tasks. Go to **Dashboard**; identify the attention count, category chart, team workload, high-priority desk and overdue tasks. Explain uploaded rows versus unique orders and that one order can have multiple exceptions. All five categories should be present.

## 0:45–1:30 — Challenge A: deliberately invalid input

In **Upload orders**, choose `samples/interview_invalid.csv`, then **Upload & evaluate orders**. Show one valid row accepted while two invalid rows are rejected. Open **Data corrections** and point to `INTERVIEW-INVALID-PHONE`, filename, row 2, field, explanation and recommended correction. Choose **Correct row**, enter `919123456789` for Phone number, and **Validate & import correction**. The corrected row imports and the issue moves into resolved history. The invalid-date row remains for correction.

## 1:30–2:15 — Challenge B: change 24 hours to 12 hours

On **Follow-up tasks**, select **Dispatch delay** and note the matching task count. Open **Business rules**, change **Dispatch threshold** from `24` to `12` and select **Save & reevaluate**. Return to the dispatch-delay queue; previously clean 18-hour confirmed orders now have tasks (including `INTERVIEW-VALID-18H`). Explain this is a saved backend setting and reevaluation uses stored orders immediately. The audit log records the change.

The ten required fields do not provide confirmation time: “If confirmed_at is available we use it; otherwise we document the order timestamp as the proxy. Date-only information gets a correction request, never a guessed time.”

## 2:15–3:00 — Challenge C: repeated uploads, no duplicate tasks

Return to **Upload orders** and import the **same sample file** twice. Show new tasks = **0** for each repeat at the same rule setting. In **Dashboard**, the uploaded-row total increases; unique orders and current task IDs remain stable. Import history shows unchanged records. Optional proof: `/api/tasks` exposes persistent task IDs and first-detection timestamps. Some boundary fixtures may age into a new exception while a long demonstration is running; tests freeze time to distinguish legitimate newly true conditions from duplicates.

## 3:00–4:00 — Challenges D and E: overdue handover and audit

Open **Follow-up tasks**, select **Failed delivery**, check **Overdue only** and choose **Manage**. These failed-attempt tasks have urgent priority and a deadline at detection. Note the task ID, current owner and deadline. Change to a different employee, set **In progress**, enter a handover note and **Save task changes**.

Reimport the original file once more. Search that task/order: its new employee and status remain unchanged. Choose **Manage → View order history**, then filter **Action** to `task_reassigned`. Show the order ID, old/new employee, **your responsible user**, precise IST timestamp and overdue flag. A page refresh preserves the record; a server restart also preserves it (verified by the backend persistence test).

## 4:00–4:35 — Filters, daily handover and resolution

On **Dashboard**, combine exception type, employee, priority and date filters; counts change from API results. Open **Daily reports**, select today’s IST date and **Download daily CSV**. Point out new detections, all unresolved exceptions, overdue/high-priority work and employee actions. New means first detected on the selected date; unresolved sections show the current snapshot.

Upload `samples/order_update_delivered.csv`: NX-1003 becomes delivered, its relevant exception task resolves, and its old history is retained. A future recurrence would create a new episode, not erase the original task.

## 4:35–5:00 — Impact and limitations

“The system automates checking, assigning and reporting so staff focus on the actual follow-up. We track overdue workload, attention rate and team queues; resolution times can be derived from stored history. Under an illustrative assumption of 200 orders/day, 90 seconds per manual check and 20 two-minute assignments, baseline admin is 340 minutes. If automated review takes 35 minutes, estimated admin savings are 305 minutes/day. This is an assumption-based example, not measured results. Missing source times, stale uploads and the confirmation-time proxy remain limitations. This local interview build has a named-user audit, not production authentication.”

Automated evidence is in `TEST_RESULTS.md`, `artifacts/pytest-results.xml`, `artifacts/browser-results.json`, and the implementation mapping in `REQUIREMENTS_CHECKLIST.md`.
