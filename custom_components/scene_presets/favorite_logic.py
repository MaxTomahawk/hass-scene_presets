"""Pure data model for per-user scene preset favorites."""


class FavoritesData:
    """Manage validated favorites while preserving user initialization state."""

    def __init__(self, valid_preset_ids, data=None):
        self._valid_preset_ids = set(valid_preset_ids)
        self._users = {}
        self._sensor_users = set()

        stored_users = (data or {}).get("users", {})
        if isinstance(stored_users, dict):
            for user_id, favorites in stored_users.items():
                if isinstance(user_id, str) and isinstance(favorites, list):
                    filtered = self._filter_stored(favorites)
                    self._users[user_id] = filtered
                    if filtered:
                        # Upgrade users that already had real favorites before
                        # sensor-user persistence existed.
                        self._sensor_users.add(user_id)

        stored_sensor_users = (data or {}).get("sensor_users", [])
        if isinstance(stored_sensor_users, list):
            self._sensor_users.update(
                user_id
                for user_id in stored_sensor_users
                if isinstance(user_id, str)
            )

    def _filter_stored(self, favorites):
        out = []
        seen = set()
        for preset_id in favorites:
            if (
                isinstance(preset_id, str)
                and preset_id in self._valid_preset_ids
                and preset_id not in seen
            ):
                seen.add(preset_id)
                out.append(preset_id)
        return out

    def _normalize(self, favorites):
        out = []
        seen = set()
        for preset_id in favorites:
            self._validate(preset_id)
            if preset_id not in seen:
                seen.add(preset_id)
                out.append(preset_id)
        return out

    def _validate(self, preset_id):
        if preset_id not in self._valid_preset_ids:
            raise ValueError(f"Unknown preset '{preset_id}'")

    def _register_sensor_user_if_needed(self, user_id, favorites):
        if favorites:
            self._sensor_users.add(user_id)

    def is_initialized(self, user_id):
        return user_id in self._users

    def get(self, user_id):
        return list(self._users.get(user_id, []))

    def sensor_user_ids(self):
        return sorted(self._sensor_users)

    def is_sensor_user(self, user_id):
        return user_id in self._sensor_users

    def set(self, user_id, favorites):
        normalized = self._normalize(favorites)
        self._users[user_id] = normalized
        self._register_sensor_user_if_needed(user_id, normalized)
        return list(normalized)

    def add(self, user_id, preset_id):
        self._validate(preset_id)
        favorites = self._users.setdefault(user_id, [])
        if preset_id not in favorites:
            favorites.append(preset_id)
        self._register_sensor_user_if_needed(user_id, favorites)
        return list(favorites)

    def remove(self, user_id, preset_id):
        self._validate(preset_id)
        favorites = self._users.setdefault(user_id, [])
        if preset_id in favorites:
            favorites.remove(preset_id)
        return list(favorites)

    def toggle(self, user_id, preset_id):
        self._validate(preset_id)
        favorites = self._users.setdefault(user_id, [])
        if preset_id in favorites:
            favorites.remove(preset_id)
        else:
            favorites.append(preset_id)
        self._register_sensor_user_if_needed(user_id, favorites)
        return list(favorites)

    def to_dict(self):
        return {
            "users": {
                user_id: list(favorites)
                for user_id, favorites in self._users.items()
            },
            "sensor_users": self.sensor_user_ids(),
        }
