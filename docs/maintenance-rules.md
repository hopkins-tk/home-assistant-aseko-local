# Maintenance rules

[Documentation](README.md) / For contributors

## Before you edit

Read the rules for the area you are changing:

- [The backwash history is checked and written in one synchronous stretch](#the-backwash-history-is-checked-and-written-in-one-synchronous-stretch)
- [Nothing is saved while a tracker is loading its store](#nothing-is-saved-while-a-tracker-is-loading-its-store)
- [An offset of `None` means "was not known", not "use the current one"](#an-offset-of-none-means-was-not-known-not-use-the-current-one)
- [Entity identity does not change](#entity-identity-does-not-change)
- [A profile reports what the frame says](#a-profile-reports-what-the-frame-says)
- [A feature never overrides its value with another live state](#a-feature-never-overrides-its-value-with-another-live-state)

Invariants that are not visible in the line being edited, each one written
down because breaking it cost real data or a wrong reading once.  They are
enforced by tests, but a test only fails after the rule is broken -- read
these before changing the code they name.

## The backwash history is checked and written in one synchronous stretch

`aseko_local.set_last_scheduled_backwash` and
`aseko_local.clear_last_scheduled_backwash` first ask every loaded entry
whether its stored history is in (`_check_backwash_history_ready` in
[`__init__.py`](../custom_components/aseko_local/__init__.py), over
`AsekoLocalDataUpdateCoordinator.loading_backwash_serials`), and only then
walk the entries and write.

**No `await` may be added between that check and the last write.**  Home
Assistant runs both in one event loop, so today nothing can run in between:
a store that finishes loading, a frame, a second service call.  An `await`
in the middle opens exactly that gap, and the call would again change one
unit and refuse another -- which is what the check was added to stop.

The check is not a transaction and does not roll anything back; it only
makes sure nothing starts that is known to be refused.

## Nothing is saved while a tracker is loading its store

`BackwashTracker.load_soon()` sets `_loading` synchronously and hands the
load to a task.  While it is set, `update()` takes no frames and
`async_save()` writes nothing, because Home Assistant's `Store` hands a
pending write back to a load in progress: a save made first would be
replaced, and the stored history was once lost that way.  The services
refuse for the same reason (`BackwashTracker.loading`).

Whatever is added to the tracker, a value that comes from the frames or
from the user must not reach the store before the load finishes.

## An offset of `None` means "was not known", not "use the current one"

The `offset_minutes` arguments of the backwash tracker default to
`CURRENT_OFFSET`, a sentinel.  An explicit `None` says the unit's clock was
not known when the valve opened, and the cycle is then compared on Home
Assistant's clock with the wider tolerance.  Do not "simplify" the sentinel
away to a plain `None` default: a clock measured later would then be used to
re-read a start it says nothing about.

## Entity identity does not change

`unique_id`s, and with them entity ids, are what users' dashboards and
automations are written against.  A rename of a translation key or a
description is fine; changing how a `unique_id` is built is not, unless it
comes with a registry migration.  Entities a unit does not have are created
disabled rather than dropped (see
[Decoding by device profile](decoding-by-device-profile.md)), so the id a
user already has keeps working.

## A profile reports what the frame says

A value is read as the unit sent it; `NOT_PRESENT` is for what the frame
says is not on the unit, never for a setting that is currently moot.  See
[Evidence rules](evidence-rules.md) and
[Decoding by device profile](decoding-by-device-profile.md).

## A feature never overrides its value with another live state

A feature decodes its own bytes -- scaling, units, enum mapping, `0xFF` to
`None`, presence -- and nothing more.  When a value only means what a user
expects in the context of another one ("heating allowed" with Heating
control off, the electrolyser output running down after a stop, HOME's
filtration switched off by hand), the user-facing value is computed from the
decoded fields:

- from one frame: a `Derived` entry in
  [`decoding/derived.py`](../custom_components/aseko_local/decoding/derived.py);
- across frames (needs history, Home Assistant's clock or a store): a
  tracker in [`trackers/`](../custom_components/aseko_local/trackers/), like
  the scheduled / manual backwash history, the clock offset and the
  consumption counters.

Either way the decoded value keeps its own field and entity (diagnostic, and
created disabled when it mostly duplicates the derived one), and an existing
entity key keeps the meaning users rely on.  Overriding inside the feature
once hid how byte[21] and byte[78] behave, and a rule written for one model
is easy to leave applying to another.  See
[Derived values](decoding-by-device-profile.md#derived-values-the-user-facing-meaning-beside-the-value-as-sent).
