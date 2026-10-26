### Task 5: Tool registry, schema validation та control policy

**Files:** `src/b12/tools/{__init__,registry,policy}.py`, `tests/unit/test_registry.py`, `tests/security/test_tool_policy.py`.

**Produces:** `ToolRegistry.register(name, description, argument_model, handler, capability)`; `.schemas(actor) -> list[dict]`; async `.execute(call: ToolCall, actor: Actor, grant: dict, cancel=None) -> ToolResult`.

- [ ] RED: invalid integer/path/extra args never reaches real handler; unknown tool gives structured error; guest cannot reuse owner grant; LLM `approved=true` argument rejected.
- [ ] Implement strict argument models, owner grants from control channel, risk classes, per-call timeout, audit hooks and exact call/result IDs.
- [ ] GREEN: handler side effect file exists only for authorized valid call; denial/timeout has no claimed success.
- [ ] Commit/review grant lifecycle and bypass cases.

## Binding architecture overrides

Spec15.1/15.4 and plan Binding review amendments override accepting actor/grant dict as proof. Add server-owned persistent ControlStore and immutable ExecutionContext (actor_id,session_id,turn_id,optional task_id,grant_id,control_revision,monotonic deadline,cancel asyncio.Event) before registry consumers. Internal DTO construction is not authentication. Registry must re-resolve current control revision/consent/capabilities/expiry/revocation and session-actor binding at dispatch and immediately before handler effect. Task7 content SessionStore binds through this control interface; no client/model request field can establish trusted actor/grant. Add focused src/b12/control.py and shared DTOs as needed; don't implement API/CLI yet.

Keep real full-host writes/argv execution enabled by valid control capabilities. Arbitrary executable/interpreter has arbitrary OS effects; argv is not a sandbox and command blacklist is not a security guarantee. Arbitrary execution requires explicit task-scoped full-execution grant OR exact executable/argv/cwd/declared-effects one-shot approval. Typed already-authorized actions must not repeatedly prompt. No external messaging/publication permission is inferred from generic full-host grant. MCP trusted catalog capabilities later Task12, not model annotations.

Persistent approval binding: exact actor/session/turn/call identity, canonical finite-JSON argument digest, capability, expiry and one-shot decision; recheck control revision after approval. Persistent tool lifecycle proposed/approved/started/completed/failed/cancelled/unknown. If crash/timeout/cancel may follow a non-idempotent effect, preserve outcome_unknown and don't replay blindly after restart; reconcile by idempotency key or owner control. Lifecycle/audit metadata contain no user text/paths/raw args, command output, display names, payload hashes as privacy substitutes. Argument-binding digest belongs private short-lived approval control state, not permanent public audit; erase it with managed control data retention.

Define shared handler/cancel/error interfaces for Task6/7; strict argument validation before any handler, cooperative cancellation and timeout via same Event/deadline as model. Task4 uses admitted requests; registry.schemas must be stable fresh copies that can enter ContextBuilder before admission. Return structured denial/errors with call/result association, never claimed success. Explicit approval_pending status must retain identity for agent resume, rather than execute automatically.

Tests use real SQLite control store/restart and real harmless temp-file handlers: guest reuse owner grant, forged actor, expired/revoked grants, stale revision, cross-session/turn/args approval replay, one-shot replay, denied LLM approval field, cancel/timeout unknown outcome and no duplicate effect on restart. Do not implement host tool bodies here. Upstream raw and completed benchmark artifacts immutable. Full suite once after focused RED/GREEN; report every API addition for downstream consumers.

