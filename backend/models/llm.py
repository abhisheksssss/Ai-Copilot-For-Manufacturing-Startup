from langchain_core.runnables import RunnableWithFallbacks
from langchain_groq import ChatGroq
from langchain_openrouter import ChatOpenRouter
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_cerebras import ChatCerebras
from core.config import settings

NEMOTRON_FREE_MODEL = "nvidia/nemotron-3.5-lightning:free"

OPENROUTER_FALLBACK_MODELS = [
    NEMOTRON_FREE_MODEL,
    "google/gemini-2.0-flash-exp:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "deepseek/deepseek-chat:free",
    "nvidia/llama-3.1-nemotron-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
]

DEPRECATED_OPENROUTER_MODELS = {
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
}


class FallbackChatModel(RunnableWithFallbacks):
    """
    Extends RunnableWithFallbacks so LangGraph's create_react_agent (.bind_tools)
    and router (.with_structured_output) work seamlessly across runtime fallbacks.
    """

    def bind_tools(self, tools, **kwargs):
        bound_primary = self.runnable.bind_tools(tools, **kwargs)
        bound_fallbacks = []
        for fb in self.fallbacks:
            if hasattr(fb, "bind_tools"):
                try:
                    bound_fallbacks.append(fb.bind_tools(tools, **kwargs))
                except Exception:
                    pass
        return FallbackChatModel(runnable=bound_primary, fallbacks=bound_fallbacks)

    def with_structured_output(self, schema, **kwargs):
        struct_primary = self.runnable.with_structured_output(schema, **kwargs)
        struct_fallbacks = []
        for fb in self.fallbacks:
            if hasattr(fb, "with_structured_output"):
                try:
                    struct_fallbacks.append(fb.with_structured_output(schema, **kwargs))
                except Exception:
                    pass
        return FallbackChatModel(runnable=struct_primary, fallbacks=struct_fallbacks)


def _get_non_openrouter_fallbacks(temperature: float, max_tokens: int) -> list:
    """Returns reliable non-OpenRouter LLM instances (Groq, NVIDIA, Gemini) as safety net."""
    backups = []

    groq_key = getattr(settings, "GROQ_API_KEY", None)
    if groq_key:
        for groq_model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            try:
                backups.append(
                    ChatGroq(
                        api_key=groq_key,
                        model_name=groq_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        max_retries=1,
                    )
                )
            except Exception:
                pass

    nvidia_key = (
        getattr(settings, "NVIDIA_API_KEY_2", None)
        or getattr(settings, "NVIDIA_API_KEY_1", None)
        or getattr(settings, "NVIDIA_API_KEY", None)
    )
    if nvidia_key:
        try:
            backups.append(
                ChatNVIDIA(
                    model="nvidia/nemotron-3-ultra-550b-a55b",
                    api_key=nvidia_key,
                    temperature=temperature,
                    top_p=0.95,
                    max_tokens=max_tokens,
                )
            )
        except Exception:
            pass

    gemini_key = getattr(settings, "GEMINI_API_KEY", None)
    if gemini_key:
        try:
            backups.append(
                ChatGoogleGenerativeAI(
                    google_api_key=gemini_key,
                    model="gemini-2.0-flash",
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
            )
        except Exception:
            pass

    return backups


def _get_openrouter_keys(start_index: int = 1) -> list[str]:
    """Returns the 3 OpenRouter API keys rotated based on start_index (1, 2, or 3)."""
    candidates = [
        getattr(settings, "OPENROUTER_API_KEY", None),
        getattr(settings, "OPENROUTER_API_KEY_2", None),
        getattr(settings, "OPENROUTER_API_KEY_3", None),
    ]
    valid = [k.strip() for k in candidates if k and isinstance(k, str) and k.strip()]
    if not valid:
        return []
    idx = (start_index - 1) % len(valid)
    rotated = valid[idx:] + valid[:idx]
    seen = set()
    res = []
    for k in rotated:
        if k not in seen:
            seen.add(k)
            res.append(k)
    return res


def _build_openrouter_with_fallbacks(
    primary_key_index: int = 1,
    primary_model: str = NEMOTRON_FREE_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 4000,
):
    if primary_model in DEPRECATED_OPENROUTER_MODELS:
        primary_model = NEMOTRON_FREE_MODEL

    keys = _get_openrouter_keys(start_index=primary_key_index)
    instances = []

    # 1. Primary model across all available OpenRouter keys (cross-key rotation)
    for k in keys:
        try:
            instances.append(
                ChatOpenRouter(
                    api_key=k,
                    model=primary_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=0,
                )
            )
        except Exception as e:
            print(f"[WARNING] Could not initialize OpenRouter model {primary_model}: {e}")

    # 2. Other fallback models on the primary key
    for model in OPENROUTER_FALLBACK_MODELS:
        if model != primary_model and keys:
            try:
                instances.append(
                    ChatOpenRouter(
                        api_key=keys[0],
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        max_retries=0,
                    )
                )
            except Exception:
                pass

    # 3. Append Groq, NVIDIA, and Gemini at the end of the runtime fallback chain
    instances.extend(_get_non_openrouter_fallbacks(temperature, max_tokens))

    if not instances:
        raise ValueError("No valid LLM instances could be initialized.")

    if len(instances) == 1:
        return instances[0]

    return FallbackChatModel(runnable=instances[0], fallbacks=instances[1:])


def get_groq_llm(
    model_name: str = "openai/gpt-oss-20b",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    groq_key = getattr(settings, "GROQ_API_KEY", None)
    if groq_key:
        try:
            return ChatGroq(
                api_key=groq_key,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=2,
            )
        except Exception:
            pass
    return get_openrouter_llm(temperature=temperature, max_tokens=max_tokens)


def get_openrouter_llm(
    model_name: str = NEMOTRON_FREE_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 4000,
):
    return _build_openrouter_with_fallbacks(
        primary_key_index=1,
        primary_model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_openrouter_llm2(
    model_name: str = NEMOTRON_FREE_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 4000,
):
    return _build_openrouter_with_fallbacks(
        primary_key_index=2,
        primary_model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_openrouter_llm3(
    model_name: str = NEMOTRON_FREE_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 4000,
):
    return _build_openrouter_with_fallbacks(
        primary_key_index=3,
        primary_model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_cerebras_llm(
    model_name: str = "gemma-4-31b",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    cerebras_key = getattr(settings, "CEREBRAS_API_KEY", None) or getattr(
        settings, "CEBREAS_API_KEY", None
    )
    if cerebras_key:
        try:
            return ChatCerebras(
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=None,
                max_retries=2,
                api_key=cerebras_key,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_mistral_llm(
    model_name: str = NEMOTRON_FREE_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    """ChatMistralAI removed as requested; delegates to OpenRouter with nvidia/nemotron-3.5-lightning:free."""
    return get_openrouter_llm3(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_gemini_llm(
    model_name: str = "gemini-2.0-flash",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    gemini_key = getattr(settings, "GEMINI_API_KEY", None)
    if gemini_key:
        try:
            return ChatGoogleGenerativeAI(
                google_api_key=gemini_key,
                model=model_name,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_planning_llm(temperature: float = 0.2, max_tokens: int = 4000):
    return get_openrouter_llm(
        model_name=NEMOTRON_FREE_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_manufacturing_llm(temperature: float = 0.2, max_tokens: int = 4000):
    return get_openrouter_llm2(
        model_name=NEMOTRON_FREE_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_scheme_llm(temperature: float = 0.2, max_tokens: int = 4000):
    return get_openrouter_llm3(
        model_name=NEMOTRON_FREE_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_research_llm(temperature: float = 0.2, max_tokens: int = 4000):
    return get_openrouter_llm(
        model_name=NEMOTRON_FREE_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_nvidia_llm(
    model_name: str = "meta/llama-3.3-70b-instruct",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    nvidia_key = getattr(settings, "NVIDIA_API_KEY", None)
    if nvidia_key:
        try:
            return ChatNVIDIA(
                api_key=nvidia_key,
                model=model_name,
                temperature=temperature,
                timeout=120,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_nvidia_llm2(
    model_name: str = "meta/llama-3.3-70b-instruct",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    key = (
        getattr(settings, "NVIDIA_API_KEY_1", None)
        or getattr(settings, "NVIDIA_API_KEY_2", None)
        or getattr(settings, "NVIDIA_API_KEY", None)
    )
    if key:
        try:
            return ChatNVIDIA(
                model=model_name,
                api_key=key,
                temperature=temperature,
                top_p=0.95,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_nvidia_2(
    model_name: str = "meta/llama-3.3-70b-instruct",
    temperature: float = 0.2,
    max_tokens: int = 2500,
):
    key = getattr(settings, "NVIDIA_API_KEY_2", None) or getattr(
        settings, "NVIDIA_API_KEY", None
    )
    if key:
        try:
            return ChatNVIDIA(
                api_key=key,
                model=model_name,
                temperature=temperature,
                timeout=45,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_nvidia_digital_twin_llm(
    model_name: str = "meta/llama-3.3-70b-instruct",
    temperature: float = 0.2,
    max_tokens: int = 2500,
):
    key = (
        getattr(settings, "NVIDIA_API_KEY_3", None)
        or getattr(settings, "NVIDIA_API_KEY_2", None)
        or getattr(settings, "NVIDIA_API_KEY", None)
    )
    if key:
        try:
            return ChatNVIDIA(
                api_key=key,
                model=model_name,
                temperature=temperature,
                timeout=30,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    groq_key = getattr(settings, "GROQ_API_KEY", None)
    if groq_key:
        try:
            return ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_fallback_llm(
    exclude_provider: str | None = "openrouter",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    """
    Returns a reliable non-OpenRouter LLM by default when primary agents fail.
    Priority: NVIDIA -> Groq -> Gemini -> OpenRouter (only if not excluded).
    """
    nvidia_key = (
        getattr(settings, "NVIDIA_API_KEY_2", None)
        or getattr(settings, "NVIDIA_API_KEY_1", None)
        or getattr(settings, "NVIDIA_API_KEY", None)
    )
    if exclude_provider != "nvidia" and nvidia_key:
        try:
            return ChatNVIDIA(
                model="meta/llama-3.3-70b-instruct",
                api_key=nvidia_key,
                temperature=temperature,
                top_p=0.95,
                max_tokens=max_tokens,
            )
        except Exception:
            pass

    groq_key = getattr(settings, "GROQ_API_KEY", None)
    if exclude_provider != "groq" and groq_key:
        try:
            return ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=2,
            )
        except Exception:
            pass

    gemini_key = getattr(settings, "GEMINI_API_KEY", None)
    if exclude_provider != "gemini" and gemini_key:
        try:
            return ChatGoogleGenerativeAI(
                google_api_key=gemini_key,
                model="gemini-2.0-flash",
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except Exception:
            pass

    if exclude_provider != "openrouter" and getattr(settings, "OPENROUTER_API_KEY", None):
        try:
            return get_openrouter_llm(temperature=temperature, max_tokens=max_tokens)
        except Exception:
            pass

    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_default_LLM(temperature: float = 0.2, max_tokens: int = 4000):
    """
    Default LLM with fallback chain.
    Priority: NVIDIA -> Groq -> Gemini -> OpenRouter
    """
    nvidia_key = (
        getattr(settings, "NVIDIA_API_KEY_2", None)
        or getattr(settings, "NVIDIA_API_KEY_1", None)
        or getattr(settings, "NVIDIA_API_KEY", None)
    )
    if nvidia_key:
        try:
            return ChatNVIDIA(
                model="nvidia/nemotron-3-ultra-550b-a55b",
                api_key=nvidia_key,
                temperature=temperature,
                top_p=0.95,
                max_tokens=max_tokens,
            )
        except Exception:
            pass

    groq_key = getattr(settings, "GROQ_API_KEY", None)
    if groq_key:
        try:
            return ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=2,
            )
        except Exception:
            pass

    gemini_key = getattr(settings, "GEMINI_API_KEY", None)
    if gemini_key:
        try:
            return ChatGoogleGenerativeAI(
                google_api_key=gemini_key,
                model="gemini-2.0-flash",
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except Exception:
            pass

    if getattr(settings, "OPENROUTER_API_KEY", None):
        return _build_openrouter_with_fallbacks(
            primary_key_index=1,
            primary_model=OPENROUTER_FALLBACK_MODELS[0],
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError("No valid LLM API keys found.")