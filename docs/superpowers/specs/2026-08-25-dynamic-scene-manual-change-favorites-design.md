# Dynamic scene manual-change stop and per-user favorites

## Scope

This change extends Scene Presets in two related areas:

1. Dynamic scenes can optionally stop when any resolved target light is turned off or its color is changed by something outside that dynamic scene. Brightness-only changes must not stop the scene.
2. Favorite presets move from browser-local storage to Home Assistant-backed, per-user storage and become controllable through Scene Presets services/actions as well as the panel.

Existing behavior remains the default unless the new options are enabled.

## Dynamic scene context model

Each `DynamicScene` owns a root `Context` for its lifetime. Every loop iteration creates one child `Context` whose `parent_id` points to the root context. The same child context is passed to every `light.turn_on` call made by that iteration, so all target-light updates caused by one preset application are causally grouped.

`apply_preset()` gains an optional `context` argument and passes it to every `hass.services.async_call("light", "turn_on", ...)`. The normal `scene_presets.apply_preset` service passes `call.context`; dynamic scenes pass their per-iteration child context.

A dynamic scene keeps the context IDs it has created for the active run. These IDs are used to distinguish scene-originated state updates from external changes. Context state is discarded when the dynamic scene stops.

## Manual-change stop option

`scene_presets.start_dynamic_scene` gains an optional boolean field:

```yaml
stop_on_manual_change: true
```

Default: `false` for backward compatibility.

UI label: **Stop on manual change**

UI description: **Stops the dynamic scene when any target light is turned off or its color is changed outside this dynamic scene. Brightness-only changes are ignored.**

When enabled, `DynamicScene` subscribes to state changes for all resolved target light entities. A single matching event stops the whole dynamic scene.

### Stop conditions

A scene stops when any watched target:

- changes from any active state to `off`; or
- remains `on` and its effective color changes, while the new state's context is not recognized as belonging to this dynamic scene.

Brightness-only changes never stop the scene.

External automations, device integrations, Hue/Zigbee apps, and direct Home Assistant user actions are treated the same: if they change color with a context that does not belong to this dynamic scene, the scene stops.

### Color comparison

Color comparison is based on the active `color_mode`, rather than comparing every derived representation (`rgb_color`, `hs_color`, `xy_color`) simultaneously.

Canonical signatures:

- `color_temp` -> `color_temp_kelvin`
- `xy` -> `xy_color`
- `hs` -> `hs_color`
- `rgb`, `rgbw`, `rgbww` -> the most appropriate available RGB-family attributes

A change in `color_mode` also counts as a color change. Small numerical tolerances may be used for float-based modes such as XY/HS to avoid stopping on harmless reporting/rounding noise.

### Listener lifecycle

The state listener is created only when `stop_on_manual_change` is enabled. It is unsubscribed when the scene stops, self-destructs, or is deleted. Stopping is idempotent so concurrent events cannot produce cleanup races.

The dynamic scene manager continues to own scene creation/deletion. Existing `stop_dynamic_scene`, `stop_dynamic_scenes_for_targets`, and `stop_all_dynamic_scenes` behavior remains compatible.

## Diagnostics and dynamic-scene state

`DynamicScene.to_dict()`/parameters expose `stop_on_manual_change`, so the panel and `get_dynamic_scenes` can display the active setting.

When a manual-change stop occurs, log the reason and triggering entity. Reasons should distinguish at least:

- `light_turned_off`
- `external_color_change`

No persistent diagnostic history is required.

## Favorites storage

Favorites currently use `window.localStorage` under `scene_presets_apply_page_favorite_presets`. The new implementation stores favorites in Home Assistant backend storage, keyed by Home Assistant user ID.

A storage helper owns the data and persists it through Home Assistant's `Store` helper. Conceptual stored data:

```json
{
  "users": {
    "<ha-user-id>": ["Rest", "Savanna sunset"]
  }
}
```

The backend validates preset IDs against known presets when modifying favorites and deduplicates entries.

## Favorites API

The integration exposes authenticated WebSocket commands for the panel:

- get current user's favorites
- replace/update current user's favorites as needed by the UI

The server derives the user from the authenticated WebSocket connection; the client never supplies an arbitrary user ID.

The integration also registers Home Assistant actions/services:

- `scene_presets.add_favorite`
- `scene_presets.remove_favorite`
- `scene_presets.toggle_favorite`

Each accepts:

```yaml
preset_id: Rest
```

For service/action calls, the backend derives the user from `call.context.user_id`. If no user context exists, the call fails with a clear validation/service error rather than modifying an arbitrary user's favorites.

This makes dashboard buttons user-specific while intentionally preventing ambiguous background automations from changing an unspecified user's favorites.

## Favorites migration

The panel continues to read the old localStorage key during migration only.

On load:

1. Fetch backend favorites for the authenticated user.
2. If that user has no initialized backend favorites and the legacy localStorage key contains preset IDs, send those favorites to the backend.
3. Mark backend favorites initialized for the user even when the resulting list is empty, so migration is not repeated indefinitely.
4. After a successful migration, the panel uses backend favorites as the source of truth. The legacy localStorage value may be removed.

This migration is intentionally per browser: a user's first browser with legacy favorites seeds backend storage; afterwards all devices share the backend value.

## Frontend changes

`PresetApplyPage` stops using `useLocalStorage` for favorites and instead loads/updates favorites through Scene Presets WebSocket commands.

The dynamic settings gain a persisted `stopOnManualChange` toggle. It is visible only when Dynamic mode is enabled and is included as `stop_on_manual_change` in the `start_dynamic_scene` payload.

The rest of the existing UI and tunable storage remains unchanged.

## Build/install behavior

Python/backend changes do not require compilation. The repository's TypeScript/React frontend does require the existing `npm run build` (`webpack`) step whenever `js/` source changes. The generated `custom_components/scene_presets/frontend/scene_presets_panel.js` must be included with the installed integration.

A Home Assistant installation therefore only needs the completed `custom_components/scene_presets` directory after the frontend bundle has already been built. The end user does not need Node/npm on Home Assistant.

After replacing/updating the custom component, Home Assistant should be restarted. A browser hard refresh/cache clear may be needed to load the new frontend bundle.

## Testing

Backend tests should cover:

- `apply_preset` forwards a supplied context to every light call.
- all lights in one dynamic iteration share one child context.
- subsequent iterations use different child contexts with the same root parent.
- own-context color updates do not stop a scene.
- external color changes stop when enabled.
- brightness-only changes do not stop.
- any watched target turning off stops when enabled.
- listeners are removed on all stop paths.
- the option defaults to disabled.
- favorites are isolated by user ID.
- add/remove/toggle are idempotent and reject unknown presets.
- service calls without `user_id` fail clearly.
- legacy frontend favorites migrate once to backend storage.

Frontend checks should cover payload generation, toggle visibility/state, favorites loading/migration/update behavior, linting, and a production webpack build.
