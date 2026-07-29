# LLM Provider Katmanı

Tüm agent'ların LLM çağrıları için kullandığı, sağlayıcıdan bağımsız merkezi katman.
Hiçbir agent OpenRouter'ı (veya başka bir sağlayıcıyı) doğrudan import etmez — hepsi
`BaseLLMProvider.generate()` / `.stream()` çağırır; hangi sağlayıcının/modelin
kullanılacağı tamamen `config/models.yaml` + `brands/{brand}/models.yaml`'dandır.

## Mimari

```
providers/llm/
├── models.py          # LLMMessage, LLMRequest, LLMResponse, LLMStreamChunk, TokenUsage
├── exceptions.py        # LLMError hiyerarşisi
├── retry.py               # exponential backoff + jitter (LLM'e özgü değil, genel amaçlı)
├── rate_limit.py            # 429 durumlarının merkezi takibi (Retry-After ayrıştırma dahil)
├── token_counter.py           # yaklaşık token sayımı (maliyet tahmini için)
├── cache.py                     # opsiyonel yanıt cache'i (arayüz + in-memory implementasyon)
├── base.py                        # BaseLLMProvider — template method (bkz. aşağı)
├── openrouter.py                    # somut implementasyon (httpx ile gerçek HTTP çağrısı)
└── factory.py                         # provider'ları isme göre inşa eden registry
```

### `BaseLLMProvider` — template method deseni

`generate()` **final**'dır (alt sınıflar override etmez); cache kontrolü, model +
`fallback_models` döngüsü, rate-limit kısa devresi, retry ve (prompt/cevap
**içermeyen**) yapılandırılmış loglamayı tek bir yerde yapar. Somut bir sağlayıcı
yalnızca üç metodu implemente eder:

- `_do_generate(request, *, model) -> LLMResponse` — TEK bir modele karşı ham çağrı.
- `stream(request, *, agent_name, run_id) -> Iterator[LLMStreamChunk]`
- `health_check() -> bool` — asla exception fırlatmaz.

Bu sayede retry/rate-limit/log mantığını yeni bir sağlayıcı eklerken **tekrar yazmazsın**.

### Hata sınıflandırması

`_do_generate`/`stream`, HTTP durum kodlarını `exceptions.py`'deki tiplere eşler.
`generate()` bunlara göre farklı davranır:

| Hata | `generate()` davranışı |
|---|---|
| `LLMTimeoutError`, `LLMProviderUnavailableError` | Aynı model için `retry.py` ile exponential backoff retry |
| `LLMRateLimitError` | Retry edilmez; `retry_after` kaydedilir (bir sonraki çağrıda o model kısa devre yapılır), bir sonraki `fallback_models` girdisine geçilir |
| `LLMAuthenticationError`, `LLMInvalidRequestError` | Hemen yükseltilir — retry/fallback denemenin faydası yok (sistemsel hata) |

`fallback_models` boşsa ve tek model başarısız olursa **asıl hata türü** (ör.
`LLMRateLimitError`) doğrudan yükselir; birden fazla model denenip hepsi başarısız
olursa `LLMAllModelsExhaustedError` (`__cause__`'da son hatayla) fırlatılır.

### Loglama

Her çağrı için: `run_id`, `agent_name`, `provider`, `model`, `prompt_tokens`,
`completion_tokens`, `duration_s`. **Prompt ve cevap içeriği varsayılan olarak
loglanmaz** — yalnızca `BaseLLMProvider(..., log_prompts=True)` ile açıkça açılırsa
DEBUG seviyesinde loglanır (yerel geliştirme/hata ayıklama için).

### Cache (opsiyonel)

`cache=None` varsayılanıyla devre dışıdır. `InMemoryLLMCache()` (veya `LLMCache`'i
implemente eden başka bir sınıf, ör. Redis-backed) `factory.create_llm_provider(...,
cache=...)` ile enjekte edilebilir. Cache anahtarı, isteğin (`LLMRequest`) deterministik
hash'idir — aynı prompt + aynı parametreler → aynı yanıt (TTL dolmadıysa).

## Yeni bir sağlayıcı ekleme

Örnek: doğrudan OpenAI API'sini eklemek.

1. `providers/llm/openai_direct.py` oluştur, `BaseLLMProvider`'ı implemente et:

   ```python
   class OpenAIDirectProvider(BaseLLMProvider):
       name = "openai-direct"
       default_api_key_env = "OPENAI_API_KEY"

       def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
           ...  # OpenAI'nin kendi endpoint'ine HTTP çağrısı + hata eşleme

       def stream(self, request, *, agent_name, run_id): ...
       def health_check(self) -> bool: ...
   ```

2. `factory.py`'nin sonuna kaydet:

   ```python
   register_provider("openai-direct", OpenAIDirectProvider)
   ```

3. `config/models.yaml` veya `brands/{brand}/models.yaml`'da ilgili agent için
   `provider: openai-direct` yaz:

   ```yaml
   agents:
     editor:
       provider: openai-direct
       model: gpt-5
   ```

**Hiçbir agent kodu değişmez.** `create_llm_provider_for_agent(settings, "editor")`
otomatik olarak yeni sağlayıcıyı inşa eder.

## Test etme

Gerçek API çağrısı yapılmadan test edilir:

- `BaseLLMProvider`'ın retry/fallback/rate-limit/cache mantığı → `tests/providers/llm/conftest.py`'deki
  `FakeLLMProvider` (sahte, kontrol edilebilir `_do_generate`) ile (bkz. `test_base.py`).
- `OpenRouterProvider`'ın HTTP/hata eşleme mantığı → `httpx.MockTransport` ile gerçek
  ağ çağrısı yapılmadan (bkz. `test_openrouter.py`).

```bash
uv run pytest tests/providers/llm -v
```
