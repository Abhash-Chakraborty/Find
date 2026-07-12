"""Tests for the thin ModelPack/PackCache contract (no real downloads)."""

import pytest

from find_api.core.model_pack import (
    ModelPack,
    PackCategory,
    PackProgress,
    PackStatus,
    NotImplementedPackCache,
)


def _sample_pack(**overrides) -> ModelPack:
    defaults = dict(
        pack_id="siglip-vit-b-16",
        category=PackCategory.EMBEDDINGS,
        version="1.0.0",
        source_url="https://example.com/siglip-vit-b-16.tar",
        license="Apache-2.0",
        size_bytes=350_000_000,
        checksum_sha256="a" * 64,
        compatible_app_versions=">=1.0.0,<2.0.0",
        config_key="model=ViT-B-16-SigLIP|pretrained=webli",
    )
    defaults.update(overrides)
    return ModelPack(**defaults)


def test_model_pack_holds_expected_fields():
    pack = _sample_pack()
    assert pack.category == PackCategory.EMBEDDINGS
    assert pack.checksum_sha256 == "a" * 64
    assert pack.size_bytes > 0


def test_model_pack_is_immutable():
    pack = _sample_pack()
    with pytest.raises(AttributeError):
        pack.version = "2.0.0"  # frozen dataclass must reject mutation


def test_pack_progress_defaults():
    progress = PackProgress(pack_id="siglip-vit-b-16", status=PackStatus.NOT_INSTALLED)
    assert progress.bytes_downloaded == 0
    assert progress.bytes_total == 0
    assert progress.error is None


def test_not_implemented_pack_cache_raises_for_every_method():
    cache = NotImplementedPackCache()
    pack = _sample_pack()

    with pytest.raises(NotImplementedError):
        cache.is_installed(pack)
    with pytest.raises(NotImplementedError):
        cache.status(pack)
    with pytest.raises(NotImplementedError):
        cache.install(pack)
    with pytest.raises(NotImplementedError):
        cache.verify(pack)
    with pytest.raises(NotImplementedError):
        cache.remove(pack)


@pytest.mark.parametrize("category", [c for c in PackCategory])
def test_all_pack_categories_constructible(category):
    pack = _sample_pack(pack_id=f"pack-{category.value}", category=category)
    assert pack.category == category
