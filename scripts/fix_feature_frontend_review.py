"""Apply runtime-review fixes to the generated feature frontend source."""

from pathlib import Path


PAGE_PATH = Path("js/pages/PresetApplyPage.tsx")


def main():
    text = PAGE_PATH.read_text(encoding="utf-8")
    old = '''    const fetchFavoritePresets = React.useCallback(() => {\n        hass.callWS({'''
    new = '''    const fetchFavoritePresets = React.useCallback(() => {\n        // Presets are loaded asynchronously on a fresh browser session. Wait\n        // before migrating legacy favorites so valid IDs are not filtered out.\n        if (presets.length === 0) {\n            return;\n        }\n\n        hass.callWS({'''

    if new not in text:
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f"favorites load guard: expected one source anchor, found {count}")
        text = text.replace(old, new, 1)

    PAGE_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
