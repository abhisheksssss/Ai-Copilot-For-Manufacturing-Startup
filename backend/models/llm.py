from langchain_groq import ChatGroq
from langchain_openrouter import ChatOpenRouter
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_cerebras import ChatCerebras
from langchain_mistralai import ChatMistralAI
from core.config import settings

def get_groq_llm(model_name: str = "llama-3.3-70b-versatile", temperature: float = 0.2, max_tokens: int = 1500):
    if not settings.GROQ_API_KEY:
        return get_openrouter_llm(temperature=temperature, max_tokens=max_tokens)
    try:
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=2,
        )
    except Exception:
        return get_openrouter_llm(temperature=temperature, max_tokens=max_tokens)


def get_openrouter_llm(model_name: str = "openai/gpt-4o-mini", temperature: float = 0.2, max_tokens: int = 1500):
    if not settings.OPENROUTER_API_KEY:
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name="llama-3.3-70b-versatile",
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=2,
        )
    return ChatOpenRouter(
        api_key=settings.OPENROUTER_API_KEY,
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_openrouter_llm2(model_name: str = "openai/gpt-4o-mini", temperature: float = 0.2, max_tokens: int = 1500):
    if settings.OPENROUTER_API_KEY_2:
        try:
            return ChatOpenRouter(
                api_key=settings.OPENROUTER_API_KEY_2,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_openrouter_llm(model_name=model_name, temperature=temperature, max_tokens=max_tokens)


def get_cerebras_llm(model_name: str = "gemma-4-31b", temperature: float = 0.2, max_tokens: int = 1500):
    if settings.CEBREAS_API_KEY:
        try:
            return ChatCerebras(
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=None,
                max_retries=2,
                api_key=settings.CEBREAS_API_KEY
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_mistral_llm(model_name: str = "mistral-large-latest", temperature: float = 0.2, max_tokens: int = 1500):
    if settings.MISTRAL_API_KEY:
        try:
            return ChatMistralAI(
                model=model_name,
                temperature=temperature,
                max_retries=2,
                api_key=settings.MISTRAL_API_KEY
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_gemini_llm(model_name: str = "gemini-2.0-flash", temperature: float = 0.2, max_tokens: int = 1500):
    if settings.GEMINI_API_KEY:
        try:
            return ChatGoogleGenerativeAI(
                google_api_key=settings.GEMINI_API_KEY,
                model=model_name,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)

def get_nvidia_llm(model_name: str = "nvidia/nemotron-3-ultra-550b-a55b", temperature: float = 0.2, max_tokens: int = 1500):
    if settings.NVIDIA_API_KEY:
        try:
            return ChatNVIDIA(
                api_key=settings.NVIDIA_API_KEY,
                model=model_name,
                temperature=temperature,
                timeout=120,
                max_tokens=max_tokens,
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_nvidia_llm2(model_name: str = "nvidia/nemotron-3-ultra-550b-a55b", temperature: float = 0.2, max_tokens: int = 1500):
    if settings.NVIDIA_API_KEY_1:
        try:
            return ChatNVIDIA(
                model=model_name,
                api_key=settings.NVIDIA_API_KEY_1,
                temperature=temperature,
                top_p=0.95,
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs":{"thinking":True,"reasoning_effort":"high"}},
            )
        except Exception:
            pass
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)

def get_nvidia_2(model_name: str = "nvidia/nemotron-3-super-120b-a12b", temperature: float = 0.2, max_tokens: int = 2000):
    key = settings.NVIDIA_API_KEY_2 or settings.NVIDIA_API_KEY
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
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_nvidia_digital_twin_llm(model_name: str = "meta/llama-3.3-70b-instruct", temperature: float = 0.2, max_tokens: int = 2000):
    key = settings.NVIDIA_API_KEY_3 or settings.NVIDIA_API_KEY_2 or settings.NVIDIA_API_KEY
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
    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_fallback_llm(exclude_provider: str = None, temperature: float = 0.2, max_tokens: int = 1500):
    """
    Returns a reliable working LLM instance (llama-3.1-8b-instant, Gemini, or OpenRouter)
    when the primary LLM (llama-3.3-70b-versatile) fails or hits a 429 Rate Limit.
    """
    if exclude_provider != "openrouter" and getattr(settings, "OPENROUTER_API_KEY", None):
        try:
            return get_openrouter_llm(temperature=temperature, max_tokens=max_tokens)
        except Exception:
            pass

    if getattr(settings, "GEMINI_API_KEY", None):
        try:
            return get_gemini_llm(temperature=temperature, max_tokens=max_tokens)
        except Exception:
            pass

    if getattr(settings, "GROQ_API_KEY", None):
        try:
            return ChatGroq(
                api_key=settings.GROQ_API_KEY,
                model_name="llama-3.1-8b-instant",
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=2,
            )
        except Exception:
            pass

    return get_default_LLM(temperature=temperature, max_tokens=max_tokens)


def get_default_LLM(temperature: float = 0.2, max_tokens: int = 1500):
    # Priority: Groq 70B -> OpenRouter -> Fallback Groq 8B
    if getattr(settings, "NVIDIA_API_KEY_2", None):
        try:
            return get_nvidia_llm2()
        except Exception:
            pass

    if settings.OPENROUTER_API_KEY:
        try:
            return ChatOpenRouter(
                api_key=settings.OPENROUTER_API_KEY,
                model="openai/gpt-4o-mini",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            pass

    if settings.GROQ_API_KEY:
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name="llama-3.1-8b-instant",
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=2,
        )

    raise ValueError("No valid LLM API keys found.")