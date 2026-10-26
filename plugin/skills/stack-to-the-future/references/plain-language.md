# Plain-language style for stages

A stage name is something a person would say about the business, not about the code.

- **Shape:** who + verb + what. "Manager approves or declines". "Days come off the balance". Max 60 characters.
- **Actors:** a role (Employee, Manager, HR) or "System" for things that happen on their own.
- **No code in names or descriptions.** File names, function names, class names and status values go only in `stageFile.label` (the bone label).
- **Banned words in stage names and descriptions:** endpoint, route handler, handler, controller, ORM, model, schema, serializer, middleware, query, payload, API, CRUD, DTO, async, task queue, callback, enum, boolean, null.
- **Branches:** a decision stage names the question ("Decide who needs to approve"); path labels give the answers ("1 day or less", "everything else").
- **Unfinished work** says so plainly: "Planned but not built: asking for it currently fails."
