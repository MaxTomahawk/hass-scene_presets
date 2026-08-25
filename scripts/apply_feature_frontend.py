"""Apply the manual-change/favorites frontend feature to the current sources.

This script is intentionally idempotent so feature CI can run it on both the
pre-patch and already-patched source tree. It uses exact source anchors and
fails loudly if upstream source no longer matches either expected form.
"""

from pathlib import Path


PAGE_PATH = Path("js/pages/PresetApplyPage.tsx")
TILE_PATH = Path("js/components/DynamicSceneTile.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source anchor, found {count}")
    return text.replace(old, new, 1)


def patch_page(text: str) -> str:
    text = replace_once(
        text,
        "    dynamicIntervalValue: 60,\n};",
        "    dynamicIntervalValue: 60,\n    stopOnManualChange: false,\n};",
        "default manual-change setting",
    )

    text = replace_once(
        text,
        "const DYNAMIC_SCENE_REFRESH_INTERVAL = 30*1000;",
        "const DYNAMIC_SCENE_REFRESH_INTERVAL = 30*1000;\nconst LEGACY_FAVORITES_KEY = \"scene_presets_apply_page_favorite_presets\";",
        "legacy favorites key",
    )

    text = replace_once(
        text,
        '    const [dynamicIntervalValue, setDynamicIntervalValue] = useLocalStorage<number>("scene_presets_apply_page_dynamic_interval_value", DEFAULT_TUNABLE_SETTINGS.dynamicIntervalValue);',
        '    const [dynamicIntervalValue, setDynamicIntervalValue] = useLocalStorage<number>("scene_presets_apply_page_dynamic_interval_value", DEFAULT_TUNABLE_SETTINGS.dynamicIntervalValue);\n    const [stopOnManualChange, setStopOnManualChange] = useLocalStorage<boolean>("scene_presets_apply_page_stop_on_manual_change", DEFAULT_TUNABLE_SETTINGS.stopOnManualChange);',
        "manual-change local setting",
    )

    text = replace_once(
        text,
        '    const [favoritePresets, setFavoritePresets] = useLocalStorage<Array<string>>("scene_presets_apply_page_favorite_presets", []);',
        '    const [favoritePresets, setFavoritePresets] = useState<Array<string>>([]);',
        "backend favorites state",
    )

    callbacks_anchor = '''    const [prettyLastActionPayload, setPrettyLastActionPayload] = useState<string>("");\n\n    const fetchActiveDynamicScenes = React.useCallback(() => {'''
    callbacks_new = '''    const [prettyLastActionPayload, setPrettyLastActionPayload] = useState<string>("");\n\n    const fetchFavoritePresets = React.useCallback(() => {\n        hass.callWS({\n            type: "scene_presets/get_favorites",\n        }).then(result => {\n            if (result?.initialized) {\n                setFavoritePresets(result.favorites ?? []);\n                window.localStorage.removeItem(LEGACY_FAVORITES_KEY);\n                return;\n            }\n\n            const validPresetIds = new Set(presets.map(preset => preset.id));\n            let legacyFavorites: Array<string> = [];\n\n            try {\n                const legacyRaw = window.localStorage.getItem(LEGACY_FAVORITES_KEY);\n                const legacyParsed = legacyRaw ? JSON.parse(legacyRaw) : [];\n\n                if (Array.isArray(legacyParsed)) {\n                    legacyFavorites = [...new Set(\n                        legacyParsed.filter(\n                            presetId => typeof presetId === "string" && validPresetIds.has(presetId)\n                        )\n                    )] as Array<string>;\n                }\n            } catch (error) {\n                console.warn("Scene Presets could not read legacy favorites", error);\n            }\n\n            return hass.callWS({\n                type: "scene_presets/set_favorites",\n                favorites: legacyFavorites,\n            }).then(saved => {\n                setFavoritePresets(saved?.favorites ?? []);\n                window.localStorage.removeItem(LEGACY_FAVORITES_KEY);\n            });\n        }).catch(error => {\n            console.warn("Scene Presets could not load favorites", error);\n        });\n    }, [hass, presets]);\n\n    const saveFavoritePresets = React.useCallback((favorites: Array<string>) => {\n        hass.callWS({\n            type: "scene_presets/set_favorites",\n            favorites: favorites,\n        }).then(result => {\n            setFavoritePresets(result?.favorites ?? []);\n        }).catch(error => {\n            console.warn("Scene Presets could not save favorites", error);\n        });\n    }, [hass]);\n\n    const fetchActiveDynamicScenes = React.useCallback(() => {'''
    text = replace_once(text, callbacks_anchor, callbacks_new, "favorites callbacks")

    text = replace_once(
        text,
        '''                    preset_id: s.parameters.preset_id,\n                    interval: s.interval,\n                    transition: s.parameters.transition\n                };''',
        '''                    preset_id: s.parameters.preset_id,\n                    interval: s.interval,\n                    transition: s.parameters.transition,\n                    stop_on_manual_change: s.parameters.stop_on_manual_change ?? false\n                };''',
        "active scene manual-change state",
    )

    text = replace_once(
        text,
        '''                    ...payload,\n                    transition: dynamicTransitionValue,\n                    interval: dynamicIntervalValue\n                };''',
        '''                    ...payload,\n                    transition: dynamicTransitionValue,\n                    interval: dynamicIntervalValue,\n                    stop_on_manual_change: stopOnManualChange\n                };''',
        "dynamic service payload",
    )

    text = replace_once(
        text,
        '''            dynamic, dynamicIntervalValue, dynamicTransitionValue,\n            fetchActiveDynamicScenes''',
        '''            dynamic, dynamicIntervalValue, dynamicTransitionValue, stopOnManualChange,\n            fetchActiveDynamicScenes''',
        "dynamic callback dependencies",
    )

    text = replace_once(
        text,
        '''                onFavClick={() => {\n                    if (!favoritePresets.includes(preset.id)) {\n                        setFavoritePresets([...favoritePresets, preset.id]);\n                    } else {\n                        setFavoritePresets(favoritePresets.filter(e => e !== preset.id));\n                    }\n                }}''',
        '''                onFavClick={() => {\n                    const nextFavorites = !favoritePresets.includes(preset.id)\n                        ? [...favoritePresets, preset.id]\n                        : favoritePresets.filter(e => e !== preset.id);\n\n                    saveFavoritePresets(nextFavorites);\n                }}''',
        "favorite tile persistence",
    )

    text = replace_once(
        text,
        '''    }, [presets, favoritePresets, handlePresetTap, setFavoritePresets]);''',
        '''    }, [presets, favoritePresets, handlePresetTap, saveFavoritePresets]);''',
        "favorite tile dependencies",
    )

    effects_anchor = '''    /**\n     * This is a hack that works around the fact that for whatever reason, componentWillUnmount never fires.'''
    effects_new = '''    useEffect(() => {\n        fetchFavoritePresets();\n    }, [fetchFavoritePresets]);\n\n    /**\n     * This is a hack that works around the fact that for whatever reason, componentWillUnmount never fires.'''
    text = replace_once(text, effects_anchor, effects_new, "favorite loading effect")

    text = replace_once(
        text,
        '''                                            setDynamic(DEFAULT_TUNABLE_SETTINGS.dynamic);\n                                            setDynamicTransitionValue(DEFAULT_TUNABLE_SETTINGS.dynamicTransitionValue);\n                                            setDynamicIntervalValue(DEFAULT_TUNABLE_SETTINGS.dynamicIntervalValue);''',
        '''                                            setDynamic(DEFAULT_TUNABLE_SETTINGS.dynamic);\n                                            setDynamicTransitionValue(DEFAULT_TUNABLE_SETTINGS.dynamicTransitionValue);\n                                            setDynamicIntervalValue(DEFAULT_TUNABLE_SETTINGS.dynamicIntervalValue);\n                                            setStopOnManualChange(DEFAULT_TUNABLE_SETTINGS.stopOnManualChange);''',
        "reset manual-change setting",
    )

    dynamic_ui_anchor = '''                                <NumberSelector\n                                    label={"Transition"}\n                                    value={dynamicTransitionValue}\n                                    setValue={(v) => setDynamicTransitionValue(v)}\n                                    minValue={0}\n                                    maxValue={300}\n                                    hass={hass}\n                                    extraSelectorProps={{"unit_of_measurement": "seconds"}}\n                                />'''
    dynamic_ui_new = dynamic_ui_anchor + '''\n\n                                <Switch\n                                    label={"Stop on manual change"}\n                                    value={stopOnManualChange}\n                                    setValue={(v) => setStopOnManualChange(v)}\n                                />\n                                <div\n                                    style={{\n                                        fontSize: "0.85rem",\n                                        opacity: 0.75,\n                                        marginLeft: "1rem",\n                                        lineHeight: "1.3rem",\n                                        marginBottom: "0.5rem"\n                                    }}\n                                >\n                                    Stops the dynamic scene when any target light is turned off or its color is changed outside this dynamic scene. Brightness-only changes are ignored.\n                                </div>'''
    text = replace_once(text, dynamic_ui_anchor, dynamic_ui_new, "manual-change toggle UI")

    text = replace_once(
        text,
        '''                                        transition={dynamicScenes[id]?.transition ?? -1}\n                                        imgSrc={imgSrc}''',
        '''                                        transition={dynamicScenes[id]?.transition ?? -1}\n                                        stopOnManualChange={dynamicScenes[id]?.stop_on_manual_change ?? false}\n                                        imgSrc={imgSrc}''',
        "active scene tile manual-change prop",
    )

    return text


def patch_tile(text: str) -> str:
    text = replace_once(
        text,
        '''    transition: number,\n    imgSrc?: string''',
        '''    transition: number,\n    stopOnManualChange: boolean,\n    imgSrc?: string''',
        "tile prop type",
    )
    text = replace_once(
        text,
        '''    transition,\n    imgSrc,''',
        '''    transition,\n    stopOnManualChange,\n    imgSrc,''',
        "tile destructuring",
    )
    text = replace_once(
        text,
        '''                    I: {interval}s, T: {transition}s''',
        '''                    I: {interval}s, T: {transition}s{stopOnManualChange ? ", Manual stop" : ""}''',
        "tile status text",
    )
    return text


def main():
    PAGE_PATH.write_text(patch_page(PAGE_PATH.read_text()), encoding="utf-8")
    TILE_PATH.write_text(patch_tile(TILE_PATH.read_text()), encoding="utf-8")


if __name__ == "__main__":
    main()
