# Per-User Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace browser-only preset favorites with persistent Home Assistant user-specific storage, expose favorite actions/services, and migrate existing browser favorites once.

**Architecture:** A pure `FavoritesData` model owns validation, ordering, initialization state, and per-user operations. A Home Assistant `Store` wrapper persists that model. Authenticated WebSocket commands serve the panel, while service actions identify the user from `call.context.user_id`.

**Tech Stack:** Python, Home Assistant Store/WebSocket/service APIs, React/TypeScript, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-dynamic-scene-manual-change-favorites-design.md`

## Global Constraints

- Favorites are keyed by Home Assistant user ID, not browser profile.
- Unknown preset IDs are rejected.
- Empty favorites still mark a user initialized so legacy migration runs once.
- Service calls without a user context fail clearly.
- Existing `scene_presets_apply_page_favorite_presets` localStorage data is migrated only when backend favorites are uninitialized.

---

### Task 1: Pure favorites model

**Files:**
- Create: `custom_components/scene_presets/favorite_logic.py`
- Test: `tests/test_favorite_logic.py`

**Interfaces:**
- `FavoritesData(valid_preset_ids, data=None)`
- `is_initialized(user_id)`, `get(user_id)`, `set(user_id, favorites)`, `add`, `remove`, `toggle`, `to_dict`

- [ ] Write failing tests for user isolation, empty initialization, stable deduplication, add/remove/toggle behavior, and unknown preset rejection.
- [ ] Run `pytest tests/test_favorite_logic.py -q` and verify missing-module failure.
- [ ] Implement the minimal model.
- [ ] Re-run tests and verify green.

### Task 2: Persistent store and service actions

**Files:**
- Create: `custom_components/scene_presets/favorites.py`
- Modify: `custom_components/scene_presets/const.py`
- Modify: `custom_components/scene_presets/__init__.py`
- Modify: `custom_components/scene_presets/services.yaml`

**Interfaces:**
- `FavoritesStore.async_get`, `async_set`, `async_add`, `async_remove`, `async_toggle`
- Services: `scene_presets.add_favorite`, `remove_favorite`, `toggle_favorite`

- [ ] Wrap Home Assistant `Store` with lazy loading and an async lock.
- [ ] Build valid preset IDs from `PRESET_DATA` including custom presets.
- [ ] Register service schemas accepting `preset_id`.
- [ ] Resolve user from `call.context.user_id`; raise `ServiceValidationError` when absent or invalid.
- [ ] Persist every mutating operation.

### Task 3: Authenticated WebSocket API

**Files:**
- Modify: `custom_components/scene_presets/websocket_api.py`
- Modify: `custom_components/scene_presets/__init__.py`

**Interfaces:**
- `scene_presets/get_favorites` -> `{favorites, initialized}`
- `scene_presets/set_favorites` with `favorites: string[]`

- [ ] Register async WebSocket handlers deriving the user from `connection.user.id`.
- [ ] Return initialized state on reads.
- [ ] Validate and persist replacement lists; return the normalized saved list.
- [ ] Return a WebSocket validation error for unknown presets.

### Task 4: Frontend migration and backend source of truth

**Files:**
- Modify: `js/pages/PresetApplyPage.tsx`

**Interfaces:**
- Legacy key: `scene_presets_apply_page_favorite_presets`
- WebSocket types: `scene_presets/get_favorites`, `scene_presets/set_favorites`

- [ ] Replace `useLocalStorage` favorites state with React state loaded from the backend.
- [ ] If backend is uninitialized, parse and validate the legacy localStorage array and send it once; use an empty list when no legacy value exists.
- [ ] Remove the legacy key only after successful migration.
- [ ] Persist favorite tile changes via WebSocket and update local state from the normalized server response.
- [ ] Run frontend lint and production webpack build in CI.

### Task 5: Installable generated frontend

**Files:**
- Modify (generated): `custom_components/scene_presets/frontend/scene_presets_panel.js`
- Create/Modify: `.github/workflows/feature-ci.yml`

- [ ] CI installs npm dependencies with `npm ci`, runs lint, and builds the production bundle.
- [ ] CI commits the generated bundle back to this feature branch when it differs, so the checked-out `custom_components/scene_presets` directory is directly installable.
- [ ] Re-run CI on the generated commit and require clean tests/build.
