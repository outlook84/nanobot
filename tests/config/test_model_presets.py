import json

import pytest

from nanobot.config.loader import load_config, save_config
from nanobot.config.schema import Config


def test_resolve_preset_returns_defaults_when_no_preset() -> None:
    config = Config()
    resolved = config.resolve_preset()
    assert resolved.model == config.agents.defaults.model
    assert resolved.provider == config.agents.defaults.provider
    assert resolved.max_tokens == config.agents.defaults.max_tokens
    assert resolved.context_window_tokens == config.agents.defaults.context_window_tokens
    assert resolved.temperature == config.agents.defaults.temperature
    assert resolved.reasoning_effort == config.agents.defaults.reasoning_effort


def test_provider_api_type_accepts_exact_values_only() -> None:
    config = Config.model_validate({
        "providers": {
            "openai": {
                "apiKey": "sk-test",
                "apiType": "responses",
            }
        }
    })
    assert config.providers.openai.api_type == "responses"

    with pytest.raises(ValueError):
        Config.model_validate({
            "providers": {
                "openai": {
                    "apiKey": "sk-test",
                    "apiType": "response",
                }
            }
        })


def test_provider_api_type_uses_registry_field_capabilities() -> None:
    with pytest.raises(ValueError, match="not supported"):
        Config.model_validate({
            "providers": {
                "custom": {
                    "apiBase": "https://example.test/v1",
                    "apiType": "responses",
                }
            }
        })


def test_resolve_provider_ref_exposes_registry_metadata() -> None:
    config = Config.model_validate({
        "providers": {
            "openai": {
                "apiKey": "sk-test",
                "apiType": "responses",
            },
        },
        "agents": {
            "defaults": {
                "model": "openai/gpt-4.1",
                "provider": "auto",
            }
        },
    })

    provider_ref = config.resolve_provider_ref()

    assert provider_ref.requested_name == "auto"
    assert provider_ref.name == "openai"
    assert provider_ref.spec is not None
    assert provider_ref.spec.supports_config_field("api_type")
    assert provider_ref.api_type == "responses"


def test_bedrock_provider_ref_exposes_region_and_profile() -> None:
    config = Config.model_validate({
        "providers": {
            "bedrock": {
                "region": "us-east-1",
                "profile": "work",
            },
        },
        "agents": {
            "defaults": {
                "model": "bedrock/anthropic.claude-opus-4-5",
                "provider": "bedrock",
            }
        },
    })

    provider_ref = config.resolve_provider_ref()

    assert provider_ref.name == "bedrock"
    assert provider_ref.spec is not None
    assert provider_ref.spec.supports_config_field("region")
    assert provider_ref.spec.supports_config_field("profile")
    assert provider_ref.region == "us-east-1"
    assert provider_ref.profile == "work"


def test_provider_alias_resolves_backend_and_overrides_config() -> None:
    config = Config.model_validate({
        "providers": {
            "openai": {
                "apiKey": "base-key",
                "apiBase": "https://api.openai.com/v1",
                "extraHeaders": {"X-Base": "1"},
            },
        },
        "providerAliases": {
            "custom-image-provider": {
                "provider": "openai",
                "apiKey": "alias-key",
                "apiBase": "https://api.example.test/v1",
                "apiType": "responses",
                "extraBody": {"tools": [{"type": "image_generation"}]},
            },
        },
        "agents": {
            "defaults": {
                "model": "gpt-5.1",
                "provider": "custom-image-provider",
            },
        },
    })

    provider_ref = config.resolve_provider_ref()
    provider = config.get_provider()

    assert provider_ref.requested_name == "custom-image-provider"
    assert provider_ref.name == "openai"
    assert provider_ref.api_type == "responses"
    assert config.get_provider_name() == "openai"
    assert config.get_api_key() == "alias-key"
    assert config.get_api_base() == "https://api.example.test/v1"
    assert provider is not None
    assert provider.extra_headers == {"X-Base": "1"}
    assert provider.extra_body == {"tools": [{"type": "image_generation"}]}
    assert config.providers.openai.api_key == "base-key"


def test_provider_alias_inherits_base_provider_fields() -> None:
    config = Config.model_validate({
        "providers": {
            "openai": {
                "apiKey": "base-key",
                "apiBase": "https://base.example.test/v1",
                "apiType": "responses",
                "extraBody": {"store": False},
            },
        },
        "providerAliases": {
            "custom-provider": {
                "provider": "openai",
                "apiBase": "https://api.example.test/v1",
            },
        },
        "agents": {
            "defaults": {
                "model": "gpt-5.1",
                "provider": "custom-provider",
            },
        },
    })

    provider = config.get_provider()

    assert config.get_provider_name() == "openai"
    assert provider is not None
    assert provider.api_key == "base-key"
    assert provider.api_base == "https://api.example.test/v1"
    assert provider.api_type == "responses"
    assert provider.extra_body == {"store": False}


def test_save_config_omits_unset_provider_alias_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config = Config.model_validate({
        "providers": {
            "openai": {
                "apiKey": "base-key",
                "apiType": "responses",
            },
        },
        "providerAliases": {
            "custom-provider": {
                "provider": "openai",
            },
        },
    })

    save_config(config, config_path)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "provider_aliases" not in data
    assert data["providerAliases"]["custom-provider"] == {"provider": "openai"}

    reloaded = load_config(config_path)
    alias_ref = reloaded._resolve_provider_alias("custom-provider")
    assert alias_ref is not None
    assert alias_ref.config.api_key == "base-key"
    assert alias_ref.config.api_type == "responses"


def test_provider_alias_preserves_explicit_null_override_after_save_load(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config = Config.model_validate({
        "providers": {
            "custom": {
                "apiKey": "base-key",
                "apiBase": "https://base.example.test/v1",
            },
        },
        "providerAliases": {
            "local-custom": {
                "provider": "custom",
                "apiKey": None,
                "apiBase": "http://localhost:11434/v1",
            },
        },
    })

    save_config(config, config_path)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["providerAliases"]["local-custom"]["apiKey"] is None
    assert data["providerAliases"]["local-custom"]["apiBase"] == "http://localhost:11434/v1"

    reloaded = load_config(config_path)
    alias_ref = reloaded._resolve_provider_alias("local-custom")
    assert alias_ref is not None
    assert alias_ref.config.api_key is None
    assert alias_ref.config.api_base == "http://localhost:11434/v1"


def test_save_config_omits_empty_provider_aliases(tmp_path) -> None:
    config_path = tmp_path / "config.json"

    save_config(Config(), config_path)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "providerAliases" not in data
    assert "provider_aliases" not in data


def test_provider_alias_preserves_explicit_auto_api_type_after_save_load(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config = Config.model_validate({
        "providers": {
            "openai": {
                "apiKey": "base-key",
                "apiType": "responses",
            },
        },
        "providerAliases": {
            "openai-auto": {
                "provider": "openai",
                "apiType": "auto",
            },
        },
        "agents": {
            "defaults": {
                "model": "gpt-4.1",
                "provider": "openai-auto",
            },
        },
    })

    save_config(config, config_path)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["providerAliases"]["openai-auto"]["apiType"] == "auto"

    reloaded = load_config(config_path)
    provider_ref = reloaded.resolve_provider_ref()
    assert provider_ref.api_type == "auto"


def test_bedrock_provider_alias_overrides_region_and_profile() -> None:
    config = Config.model_validate({
        "providers": {
            "bedrock": {
                "region": "us-east-1",
                "profile": "default",
            },
        },
        "providerAliases": {
            "bedrock-eu": {
                "provider": "bedrock",
                "region": "eu-west-1",
                "profile": "prod",
            },
        },
        "agents": {
            "defaults": {
                "model": "bedrock/anthropic.claude-opus-4-5",
                "provider": "bedrock-eu",
            },
        },
    })

    provider_ref = config.resolve_provider_ref()

    assert provider_ref.name == "bedrock"
    assert provider_ref.region == "eu-west-1"
    assert provider_ref.profile == "prod"
    assert config.providers.bedrock.region == "us-east-1"
    assert config.providers.bedrock.profile == "default"


def test_provider_alias_rejects_builtin_name() -> None:
    with pytest.raises(ValueError, match="conflicts with a built-in provider"):
        Config.model_validate({
            "providerAliases": {
                "openai": {
                    "provider": "openai",
                    "apiKey": "alias-key",
                },
            },
        })


def test_provider_alias_rejects_reserved_auto_name() -> None:
    with pytest.raises(ValueError, match="conflicts with a built-in provider"):
        Config.model_validate({
            "providerAliases": {
                "auto": {
                    "provider": "openai",
                    "apiKey": "alias-key",
                },
            },
        })


def test_provider_alias_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="targets unknown provider"):
        Config.model_validate({
            "providerAliases": {
                "unknown-alias": {
                    "provider": "missing",
                    "apiKey": "alias-key",
                },
            },
        })


def test_provider_alias_rejects_oauth_provider() -> None:
    with pytest.raises(ValueError, match="cannot target OAuth provider"):
        Config.model_validate({
            "providerAliases": {
                "codex-alt": {
                    "provider": "openai_codex",
                },
            },
        })


def test_provider_alias_rejects_unsupported_config_field() -> None:
    with pytest.raises(ValueError, match="api_type is not supported"):
        Config.model_validate({
            "providerAliases": {
                "anthropic-responses": {
                    "provider": "anthropic",
                    "apiType": "responses",
                    "apiKey": "alias-key",
                },
            },
        })

    with pytest.raises(ValueError, match="region is not supported"):
        Config.model_validate({
            "providerAliases": {
                "openai-eu": {
                    "provider": "openai",
                    "apiKey": "alias-key",
                    "region": "eu-west-1",
                },
            },
        })


def test_legacy_defaults_config_without_presets_still_resolves() -> None:
    config = Config.model_validate({
        "agents": {
            "defaults": {
                "model": "openai/gpt-4.1",
                "provider": "openai",
                "maxTokens": 4096,
                "contextWindowTokens": 128_000,
                "temperature": 0.2,
                "reasoningEffort": "low",
            }
        }
    })

    resolved = config.resolve_preset()
    assert config.agents.defaults.model_preset is None
    assert config.model_presets == {}
    assert resolved.model == "openai/gpt-4.1"
    assert resolved.provider == "openai"
    assert resolved.max_tokens == 4096
    assert resolved.context_window_tokens == 128_000
    assert resolved.temperature == 0.2
    assert resolved.reasoning_effort == "low"


def test_resolve_preset_returns_active_preset() -> None:
    config = Config.model_validate({
        "model_presets": {
            "fast": {
                "model": "openai/gpt-4.1",
                "provider": "openai",
                "maxTokens": 4096,
                "contextWindowTokens": 32_768,
                "temperature": 0.5,
                "reasoningEffort": "low",
            }
        },
        "agents": {
            "defaults": {
                "modelPreset": "fast",
            }
        },
    })
    resolved = config.resolve_preset()
    assert resolved.model == "openai/gpt-4.1"
    assert resolved.provider == "openai"
    assert resolved.max_tokens == 4096
    assert resolved.context_window_tokens == 32_768
    assert resolved.temperature == 0.5
    assert resolved.reasoning_effort == "low"


def test_default_preset_is_agents_defaults_even_when_named_preset_is_active() -> None:
    config = Config.model_validate({
        "agents": {
            "defaults": {
                "model": "openai/gpt-4.1",
                "provider": "openai",
                "modelPreset": "fast",
            }
        },
        "modelPresets": {
            "fast": {"model": "openai/gpt-4.1-mini", "provider": "openai"},
        },
    })

    assert config.resolve_preset().model == "openai/gpt-4.1-mini"
    assert config.resolve_preset("default").model == "openai/gpt-4.1"


def test_model_presets_accepts_camel_case_root_key() -> None:
    config = Config.model_validate({
        "modelPresets": {
            "fast": {
                "model": "openai/gpt-4.1",
                "provider": "openai",
            }
        },
    })

    assert config.model_presets["fast"].model == "openai/gpt-4.1"
    assert config.model_presets["fast"].provider == "openai"


def test_resolve_preset_can_target_named_preset_without_activating() -> None:
    config = Config.model_validate({
        "model_presets": {
            "fast": {"model": "openai/gpt-4.1", "provider": "openai"},
            "deep": {"model": "anthropic/claude-opus-4-5", "provider": "anthropic"},
        },
        "agents": {"defaults": {"modelPreset": "fast"}},
    })

    resolved = config.resolve_preset("deep")
    assert resolved.model == "anthropic/claude-opus-4-5"
    assert resolved.provider == "anthropic"


def test_validator_rejects_unknown_preset() -> None:
    import pytest
    with pytest.raises(ValueError, match="model_preset 'unknown' not found in model_presets"):
        Config.model_validate({
            "agents": {
                "defaults": {
                    "modelPreset": "unknown",
                }
            }
        })


def test_model_preset_accepts_explicit_default_name() -> None:
    config = Config.model_validate({
        "agents": {
            "defaults": {
                "model": "openai/gpt-4.1",
                "modelPreset": "default",
            }
        }
    })

    assert config.resolve_preset().model == "openai/gpt-4.1"


def test_model_presets_rejects_reserved_default_name() -> None:
    import pytest

    with pytest.raises(ValueError, match="model_preset name 'default' is reserved"):
        Config.model_validate({
            "modelPresets": {
                "default": {"model": "custom-model"},
            },
        })


def test_resolve_preset_rejects_unknown_named_preset() -> None:
    import pytest
    with pytest.raises(KeyError, match="model_preset 'missing' not found"):
        Config().resolve_preset("missing")


def test_match_provider_uses_preset_model() -> None:
    config = Config.model_validate({
        "providers": {
            "openai": {"apiKey": "sk-test"},
        },
        "model_presets": {
            "fast": {
                "model": "openai/gpt-4.1",
                "provider": "openai",
            }
        },
        "agents": {
            "defaults": {
                "modelPreset": "fast",
            }
        },
    })
    name = config.get_provider_name()
    assert name == "openai"


def test_match_provider_uses_preset_provider_when_forced() -> None:
    config = Config.model_validate({
        "providers": {
            "anthropic": {"apiKey": "sk-test"},
        },
        "model_presets": {
            "fast": {
                "model": "anthropic/claude-opus-4-5",
                "provider": "anthropic",
            }
        },
        "agents": {
            "defaults": {
                "modelPreset": "fast",
            }
        },
    })
    name = config.get_provider_name()
    assert name == "anthropic"


def test_match_provider_routes_forced_novita_model_api_models() -> None:
    config = Config.model_validate({
        "providers": {
            "novita": {"apiKey": "sk-test"},
        },
        "agents": {
            "defaults": {
                "model": "deepseek-v4-pro",
                "provider": "novita",
            }
        },
    })

    assert config.get_provider_name() == "novita"
    assert config.get_api_base() == "https://api.novita.ai/openai"
