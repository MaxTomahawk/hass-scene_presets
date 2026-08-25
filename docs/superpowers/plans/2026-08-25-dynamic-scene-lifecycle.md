# Dynamic Scene Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep dynamic scenes running reliably for repeated iterations while distinguishing scene-issued color progress from genuine external color changes.

**Architecture:** Separate planning of per-light color moves from service execution so `DynamicScene` knows the expected target for each light before a command is sent. Track bounded context IDs and per-light expected moves, and make the background task self-cleaning on exceptions instead of leaving zombie scenes in the manager.

**Tech Stack:** Home Assistant custom integration, Python asyncio, Home Assistant `Context`, state-change listeners, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-v2.8-favorites-sensors-dynamic-loop-design.md`

## Global Constraints

- `off` always stops when manual-change stop is enabled.
- Brightness-only never stops.
- Unknown explicit user color changes stop immediately.
- No fixed two-second contextless grace heuristic.
- The loop must be tested across at least five real iterations.

---

### Task 1: Reproduce lifecycle failures

**Files:**
- Modify: `tests/test_dynamic_scene.py`

**Interfaces:**
- Test helper executes the actual `_loop()` with controlled sleep/apply behavior for at least five iterations.

- [ ] Add a failing test proving five iterations continue when no external change occurs.
- [ ] Add a failing test proving an exception in an iteration removes/stops the scene deterministically and records an error instead of leaving `running: true`.
- [ ] Add a failing test proving stored target lists are not mutated by shuffle.
- [ ] Run focused tests and confirm failures.

### Task 2: Split color planning from execution

**Files:**
- Modify: `custom_components/scene_presets/presets.py`
- Create: `custom_components/scene_presets/color_moves.py`
- Test: `tests/test_color_moves.py`

**Interfaces:**
- `build_light_moves(hass, preset_id, light_entity_ids, transition, shuffle, smart_shuffle, brightness_override) -> list[LightMove]`.
- `LightMove` records `entity_id`, service payload, source color signature, target color signature, transition seconds.
- `apply_light_moves(hass, moves, context=None)` executes service calls without mutating caller-owned target lists.
- Existing `apply_preset()` remains as compatibility wrapper that builds then applies moves.

- [ ] Write failing tests for move planning, deterministic ownership/non-mutation, and XY/color-temperature target signatures.
- [ ] Run focused tests and verify failure.
- [ ] Implement focused move planner/executor and wrapper.
- [ ] Run tests and commit.

### Task 3: Expected move tracking and bounded contexts

**Files:**
- Modify: `custom_components/scene_presets/manual_change.py`
- Modify: `custom_components/scene_presets/dynamic_scenes.py`
- Test: `tests/test_dynamic_scene.py`
- Test: `tests/test_manual_change.py`

**Interfaces:**
- Per-light expected move contains source signature, target signature, command monotonic time, transition duration.
- A helper classifies a state report as `own_progress`, `external_color`, `brightness_only`, or `off`.
- Retain only a bounded number of recent scene context IDs sufficient for in-flight updates.

- [ ] Write failing tests for contextless XY progress toward target, target reached, divergent XY change, color-temperature progress, explicit user override, brightness-only, and stale post-transition report.
- [ ] Write failing test proving context retention remains bounded after hundreds of cycles.
- [ ] Run focused tests and verify failure.
- [ ] Replace the fixed grace heuristic with expected-move classification.
- [ ] Record expected moves before executing each scene cycle.
- [ ] Bound context storage using a deque/set pair or timestamped map.
- [ ] Run tests and commit.

### Task 4: Lifecycle-safe task completion

**Files:**
- Modify: `custom_components/scene_presets/dynamic_scenes.py`
- Test: `tests/test_dynamic_scene.py`

**Interfaces:**
- `to_dict()` includes `running`, `stop_reason`, and `last_error`.
- Unexpected iteration exceptions are logged and trigger manager cleanup exactly once.

- [ ] Write/finish failing lifecycle tests for clean stop and unexpected exception.
- [ ] Implement guarded loop/finalization and idempotent manager deletion.
- [ ] Ensure cancellation is not reported as an error.
- [ ] Run the five-iteration and exception tests and commit.

### Task 5: Dynamic scene verification

**Files:**
- Modify only if required by validation.

- [ ] Run the entire Python test suite.
- [ ] Run Python compile.
- [ ] Run frontend lint/build and verify the committed bundle remains correct.
- [ ] Run Hassfest.
- [ ] Commit validation-only corrections.

### Task 6: v2.8.0 release

**Files:**
- Modify: `custom_components/scene_presets/manifest.json`
- Create: `.github/releases/v2.8.0.md`

- [ ] Bump version to `2.8.0` and write release notes covering both approved subsystems.
- [ ] Run all exact-release checks again.
- [ ] Verify feature branch is a clean fast-forward of `master`.
- [ ] Fast-forward `master` only after every check is green.
- [ ] Verify the release workflow publishes `v2.8.0` targeting the exact master commit.
