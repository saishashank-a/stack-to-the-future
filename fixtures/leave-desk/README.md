# Leave Desk (test fixture)

A small time-off app written for Stack to the Future's tests. It is not meant to run in production.

**Rules**

- Requests of 1 day or less are approved automatically.
- Managers may approve their own requests of up to 3 days.
- Everything else goes to the requester's manager, who approves or declines.
- Approved leave is deducted from the balance and the employee is emailed.
- On the 1st of each month HR gets an email summary of approved leave.

**Planted on purpose** (the atlas must find these)

- `LeaveStatus.CANCELLED` exists but nothing ever sets it (missing transition).
- `reports.service.export_csv` raises `NotImplementedError` (stub).
- A TODO in `leave/balance.py`.
- Fake credentials in `app/core/config.py` and `.env.example` that must never appear in any output.
