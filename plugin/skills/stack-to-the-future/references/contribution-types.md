# Contribution types

Every file on a stage, and every file card, gets exactly one type. Pick the first that fits.

| Type | Test | Leave Desk example |
|---|---|---|
| **Owner** | The stage would not happen without this file's own logic. | `leave/service.py` owns *Decide who needs to approve* |
| **Helper** | Does real work for the stage but only for this module, and the stage's rules live elsewhere. | `leave/schemas.py` checks the form on *Employee asks for time off* |
| **Shared system** | Used by stages in more than one workflow or module, and does one service for all of them. | `shared/notifications.py` sends every email |
| **Foundation** | Plumbing: settings, secrets loading, DB connection, start-up wiring, dependency lists, empty `__init__.py`. Gets no card; goes in a foundation group. | `core/database.py` |

A file can be Owner on one stage and Helper on another (a stage-level choice). Its card uses the type it has on most stages.

**"What breaks if this file is gone"** describes the effect a user would notice, not the import error. Good: "Managers never hear about requests waiting for them." Bad: "ImportError in service.py."
