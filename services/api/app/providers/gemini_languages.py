"""Idiomas de DESTINO do Gemini 3.5 Live Translate, conforme a tabela da documentação oficial
(ai.google.dev/gemini-api/docs/live-api/live-translate, lida em 2026-11-16).

IMPORTANTE: o Gemini NÃO oferece uma chamada de API para listar idiomas; esta lista vem da DOCUMENTAÇÃO (não da API) e
por isso as capacidades ficam `verified=False` até haver teste real por idioma. Se o Google mudar a tabela, atualize aqui.
Nossos códigos: "pt" = pt-BR (português do Brasil); "pt-PT" separado; "no" = norueguês (a doc lista "no, nb").
"""
GEMINI_LANGS: dict[str, str] = {
    "af": "Afrikaans", "ak": "Akan", "sq": "Albanian", "am": "Amharic", "ar": "Arabic", "hy": "Armenian", "az": "Azerbaijani",
    "eu": "Basque", "be": "Belarusian", "bn": "Bengali", "bg": "Bulgarian", "my": "Burmese", "ca": "Catalan",
    "zh-Hans": "Chinese (Simplified)", "zh-Hant": "Chinese (Traditional)", "hr": "Croatian", "cs": "Czech", "da": "Danish",
    "nl": "Dutch", "en": "English", "et": "Estonian", "fil": "Filipino", "fi": "Finnish", "fr": "French", "gl": "Galician",
    "ka": "Georgian", "de": "German", "el": "Greek", "gu": "Gujarati", "ha": "Hausa", "he": "Hebrew", "hi": "Hindi",
    "hu": "Hungarian", "is": "Icelandic", "id": "Indonesian", "it": "Italian", "ja": "Japanese", "jv": "Javanese",
    "kn": "Kannada", "kk": "Kazakh", "km": "Khmer", "rw": "Kinyarwanda", "ko": "Korean", "lo": "Lao", "lv": "Latvian",
    "lt": "Lithuanian", "mk": "Macedonian", "ms": "Malay", "ml": "Malayalam", "mr": "Marathi", "mn": "Mongolian",
    "ne": "Nepali", "no": "Norwegian", "fa": "Persian", "pl": "Polish", "pt": "Portuguese (Brazil)", "pt-PT": "Portuguese (Portugal)",
    "pa": "Punjabi", "ro": "Romanian", "ru": "Russian", "sr": "Serbian", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "es": "Spanish", "su": "Sundanese", "sw": "Swahili", "sv": "Swedish", "ta": "Tamil", "te": "Telugu",
    "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese", "zu": "Zulu",
}

# nosso código -> código que a API do Gemini espera (só onde difere)
TO_API = {"pt": "pt-BR"}


def api_code(lang: str) -> str:
    return TO_API.get(lang, lang)
