# Dynamic Scene Manual-Change Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add causal contexts to preset light calls and optionally stop a dynamic scene when any target is turned off or externally changes color, while ignoring brightness-only changes.

**Architecture:** `apply_preset()` accepts an optional Home Assistant `Context`. Each `DynamicScene` owns a root context and creates one child context per loop iteration, shared across all target-light service calls in that iteration. A state listener compares canonical color attributes and stops only for off events or external color changes.

**Tech Stack:** Python, Home Assistant custom integration APIs, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-dynamic-scene-manual-change-favorites-design.md`

## Global Constraints

- `stop_on_manual_change` defaults to `false`.
- Brightness-only state changes never stop a dynamic scene.
- Any resolved target turning off stops the whole scene when the option is enabled.
- All light calls in one iteration share one child context; later iterations use new child contexts with the same root parent.
- State listeners are always removed when the scene stops.

---

### Task 1: Color and context classification

**Files:**
- Create: `custom_components/scene_presets/manual_change.py`
- Test: `tests/test_manual_change.py`

**Interfaces:**
- Produces: `color_changed(old_attributes, new_attributes) -> bool`
- Produces: `is_scene_context(context_id, parent_id, root_context_id, own_context_ids) -> bool`

- [ ] Write tests for brightness-only changes, XY changes, color-temperature changes, color-mode changes, own IDs, root-parent IDs, child-parent IDs, and unknown contexts.
- [ ] Run `pytest tests/test_manual_change.py -q` and verify it fails because `manual_change.py` does not exist.
- [ ] Implement canonical color signatures and context classification.
- [ ] Re-run the test and verify it passes.

### Task 2: Propagate contexts through preset application

**Files:**
- Modify: `custom_components/scene_presets/presets.py`
- Modify: `custom_components/scene_presets/__init__.py`
- Test: `tests/test_dynamic_scene.py`

**Interfaces:**
- `apply_preset(..., brightness_override=None, context=None)`

- [ ] Add a failing test that passes a sentinel context to `apply_preset()` and asserts every `light.turn_on` call receives the same object.
- [ ] Run the targeted test and verify the current signature fails.
- [ ] Add the optional `context` argument and forward it to every `hass.services.async_call`.
- [ ] Pass `call.context` from the normal `apply_preset` service.
- [ ] Re-run the targeted test.

### Task 3: Dynamic-scene root/child contexts and manual-stop listener

**Files:**
- Modify: `custom_components/scene_presets/dynamic_scenes.py`
- Modify: `custom_components/scene_presets/const.py`
- Modify: `custom_components/scene_presets/__init__.py`
- Modify: `custom_components/scene_presets/services.yaml`
- Test: `tests/test_dynamic_scene.py`

**Interfaces:**
- `DynamicScene(..., parent_context=None)`
- `DynamicScene._new_step_context() -> Context`
- Service field: `stop_on_manual_change: bool`

- [ ] Add failing tests proving step contexts are unique with the same root parent, own-context color changes are ignored, external color changes stop, brightness-only changes are ignored, and target-off stops.
- [ ] Run the targeted tests and verify failures are caused by missing behavior.
- [ ] Implement root and step contexts, register step IDs before `apply_preset`, and pass the child context to all calls in an iteration.
- [ ] Register `async_track_state_change_event` only when `stop_on_manual_change` is true.
- [ ] Implement idempotent listener cleanup and stop-reason logging.
- [ ] Add schema/service metadata with backwards-compatible default `false`.
- [ ] Re-run tests and Python compile checks.

### Task 4: Frontend toggle and active-scene indicator

**Files:**
- Modify: `js/pages/PresetApplyPage.tsx`
- Modify: `js/components/DynamicSceneTile.tsx`

**Interfaces:**
- Local setting key: `scene_presets_apply_page_stop_on_manual_change`
- Service payload field: `stop_on_manual_change`

- [ ] Add the persisted toggle to dynamic tunables, include it in the start payload, and reset it with other tunables.
- [ ] Include `stop_on_manual_change` in fetched active-scene display data.
- [ ] Show a concise marker on active dynamic-scene tiles.
- [ ] Run `npm run lint` and `npm run build` in CI.
