# `app/leave/service.py`

## What this file is for

This is the rulebook for time off. It decides who has to approve a request, records approvals and refusals, takes approved days off the balance, and starts the emails. It does the real work behind almost every stage of the "Request time off" workflow: asking for time off, deciding who approves, the three approval routes, the manager's decision, and taking the days off.

## Step by step

### 1. Decide who needs to approve

Every request gets one of three routes. A request of one day or less is approved automatically. A manager asking for up to three days approves it themselves. Everything else goes to the requester's manager. The day limits come from the app's settings, so they can be changed without touching this file.

`app/leave/service.py:13-19 choose_route`

### 2. Take in a new request

When an employee asks for time off, the request is refused straight away if they don't have enough days left. Otherwise it is saved, given its route from step 1, and written to the audit log.

`app/leave/service.py:22-29 submit_request`

### 3. Send it down the right route

Short requests are approved on the spot, a manager's own short break is approved in their name, and anything else triggers an email asking the manager to review it. All of this happens before the employee gets an answer back.

`app/leave/service.py:30-37 submit_request`

### 4. The two instant approvals

These two small pieces exist so the automatic route and the self-approval route read clearly. Both hand over to the shared approval step in step 7; the only difference is whose name goes on the approval (nobody for automatic, the manager themselves for self-approval).

`app/leave/service.py:40-41 approve_directly` and `app/leave/service.py:44-45 self_approve`

### 5. The manager says yes

When a manager approves, the file first checks they are allowed to decide (step 6), then runs the shared approval step and saves.

`app/leave/service.py:48-52 approve_by_manager`

### 6. The manager says no

A refusal goes through the same permission check, marks the request as declined, records who declined it, logs it, and emails the employee. Nothing comes off their balance.

`app/leave/service.py:55-62 reject_by_manager`

### 7. Who is allowed to decide

A request can only be decided once: if it is no longer waiting, the decision is refused. Only the requester's own manager, or someone in HR, may decide it.

`app/leave/service.py:65-69 _check_reviewer`

### 8. What every approval does

All three approval routes meet here. The request is marked approved, the approver is recorded, the days are taken off the employee's balance, the approval is logged, and the employee is emailed the outcome.

`app/leave/service.py:72-77 _approve`

## Where it hands off

- The number of days to take off → the balance bookkeeping `app/leave/service.py:75 _approve`
- "Please review" and "here's the decision" emails → the background email jobs `app/leave/service.py:35 submit_request`, `app/leave/service.py:60 reject_by_manager`, `app/leave/service.py:77 _approve`
- Who did what, and when → the audit log `app/leave/service.py:29 submit_request`

## What breaks if it's gone

Requests can't be routed, approved or declined, so every time-off action in the app fails. The screens would still load, but nothing behind them would work.

## Open issues

- Booked leave can't be cancelled: the app has a "cancelled" state, but nothing in this file (or anywhere else) ever moves a request into it, and there is no way to give the days back. `app/leave/models.py:21 LeaveStatus.CANCELLED`
