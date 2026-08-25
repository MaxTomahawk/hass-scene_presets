# Favorites Sensors and Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Scene Presets favorites as persistent per-user Home Assistant sensors and allow favorite actions to target an explicit user safely.

**Architecture:** Extend `FavoritesStore` with persisted sensor-user membership and update listeners, add a `sensor` platform with one entity per registered favorite user, and centralize action user resolution/authorization. Existing WebSocket commands remain scoped to `connection.user`.

**Tech Stack:** Home Assistant custom integration, Python 3.13, `SensorEntity`, config-entry forwarding, Home Assistant auth/user APIs, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-v2.8-favorites-sensors-dynamic-loop-design.md`

## Global Constraints

- No custom Lovelace card.
- Sensor unique IDs are based on Home Assistant user IDs.
- Opening the Scene Presets page with an empty migrated favorite list must not create a sensor.
- Once a user sensor is created, it remains available when favorites become empty.
- Existing WebSocket behavior remains self-user-only.

---

### Task 1: Favorites store sensor registration and listeners

**Files:**
- Modify: `custom_components/scene_presets/favorite_logic.py`
- Modify: `custom_components/scene_presets/favorites.py`
- Test: `tests/test_favorite_logic.py`
- Test: `tests/test_favorites_store.py`

**Interfaces:**
- Produces: `FavoritesData.sensor_user_ids() -> list[str]`, `FavoritesData.ensure_sensor_user(user_id) -> bool`
- Produces: `FavoritesStore.async_sensor_user_ids()`, `FavoritesStore.async_subscribe(user_id, callback)`, store mutations notify callbacks after save.

- [ ] Write failing pure-model tests proving empty initialization does not register a sensor user, first non-empty add/set does, and the registration persists after favorites become empty.
- [ ] Run the focused tests and verify failure.
- [ ] Add persisted `sensor_users` data and model helpers.
- [ ] Add store subscriptions and mutation notifications.
- [ ] Run focused tests and commit.

### Task 2: Per-user sensor platform

**Files:**
- Create: `custom_components/scene_presets/sensor.py`
- Modify: `custom_components/scene_presets/__init__.py`
- Test: `tests/test_favorites_sensor.py`

**Interfaces:**
- Sensor unique ID: `scene_presets_favorites_<user_id>`
- State: favorite count.
- Attributes: `user_id`, `user_name`, `favorite_ids`, `favorite_names`.

- [ ] Write failing tests for one registered user sensor, live updates, persistence with zero favorites, and no sensor for an initialized-but-never-favorited user.
- [ ] Run focused tests and verify failure.
- [ ] Forward the config entry to the `sensor` platform.
- [ ] Implement dynamic entity addition for newly registered sensor users and store subscriptions for updates.
- [ ] Resolve current user display name from Home Assistant auth without making it part of entity identity.
- [ ] Run focused tests and commit.

### Task 3: Explicit-user favorite actions

**Files:**
- Modify: `custom_components/scene_presets/__init__.py`
- Modify: `custom_components/scene_presets/const.py`
- Modify: `custom_components/scene_presets/services.yaml`
- Test: `tests/test_favorite_actions.py`

**Interfaces:**
- Optional action field: `user_id`.
- New action: `scene_presets.set_favorites` with `favorites: list[str]`.
- User-resolution rules exactly match the spec.

- [ ] Write failing tests for self-user defaulting, explicit admin target, explicit non-admin cross-user rejection, contextless automation with explicit user, invalid user ID, and `set_favorites`.
- [ ] Run focused tests and verify failure.
- [ ] Implement a single async user resolver/authorizer used by all favorite actions.
- [ ] Register `set_favorites` and extend schemas/descriptions for optional `user_id`.
- [ ] Run focused tests and commit.

### Task 4: Favorites integration verification

**Files:**
- Modify only if required by validation.

- [ ] Run all Python tests.
- [ ] Run `python -m compileall custom_components/scene_presets`.
- [ ] Run Hassfest.
- [ ] Review storage backward compatibility: existing `{users: ...}` files load with empty `sensor_users`.
- [ ] Commit any validation-only corrections.
