"""Logo da organização: validação e re-gravação segura da imagem enviada.

Por que decodificar e regravar (em vez de guardar o arquivo como veio)?
 - garante que é MESMO uma imagem (não confiamos em extensão nem no tipo declarado pelo navegador);
 - remove metadados (EXIF/GPS) e qualquer dado escondido no arquivo;
 - padroniza tamanho (máx. 512 px) e formato (PNG), então o site sempre serve algo previsível.
SVG não é aceito: pode conter script e viraria XSS armazenado.
"""
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .editorial import STORAGE

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 512
MAX_PIXELS = 25_000_000  # proteção contra "bomba de descompressão" (imagem pequena que explode na memória)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class LogoError(ValueError):
    pass


def logo_path(tenant_id: str) -> Path:
    """Caminho do logo DENTRO da pasta do tenant (nunca vem do usuário => sem path traversal)."""
    return STORAGE / tenant_id / "branding" / "logo.png"


def process_logo(raw: bytes) -> bytes:
    if not raw:
        raise LogoError("Arquivo vazio.")
    if len(raw) > MAX_BYTES:
        raise LogoError("Imagem muito grande (máximo 2 MB).")
    try:
        img = Image.open(io.BytesIO(raw))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise LogoError("Formato não aceito. Use PNG, JPG ou WebP.")
        img.load()
    except LogoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise LogoError("Arquivo de imagem inválido.")
    img = img.convert("RGBA")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
