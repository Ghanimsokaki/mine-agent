from src.config import DEFAULT_ADMIN_EMAIL, HF_CHAT_ENDPOINT, REQUESTED_HF_MODEL, load_config
from src.llm import available_models


def test_defaults_use_huggingface_gemby_and_configured_admin():
    config = load_config({})
    assert config.huggingface_model == REQUESTED_HF_MODEL
    assert config.huggingface_endpoint == HF_CHAT_ENDPOINT
    assert config.admin_email == DEFAULT_ADMIN_EMAIL
    assert not config.has_huggingface


def test_model_picker_choices_keep_gemby_on_huggingface():
    primary, nemotron, *_ = available_models("hwiiiiiiii/gemby-agent-3b", "nvidia/nemotron")
    assert primary.provider == "huggingface"
    assert primary.model_id == "hwiiiiiiii/gemby-agent-3b"
    assert nemotron.provider == "openrouter"
