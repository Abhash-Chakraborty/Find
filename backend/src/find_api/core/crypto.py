"""Vault crypto helpers."""

from __future__ import annotations

import os
import tempfile
import time
import threading
from pathlib import Path
from typing import Dict, Iterator

import argon2
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

active_vault_sessions: Dict[str, tuple[bytes, float]] = {}
_sessions_lock = threading.Lock()
SESSION_TTL_SECONDS = 3600

VAULT_STORAGE_DIR = Path(__file__).resolve().parents[3] / "vault_storage"
_AES_KEY_SIZE = 32
_GCM_IV_SIZE = 12
_GCM_TAG_SIZE = 16
_CHUNK_SIZE = 1024 * 1024
_VAULT_VERIFIER_PLAINTEXT = b"find-vault-verifier-v1"


def derive_master_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a vault master key from the user passphrase and vault salt."""
    return argon2.low_level.hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=_AES_KEY_SIZE,
        type=argon2.low_level.Type.ID,
        version=argon2.low_level.ARGON2_VERSION,
    )


def create_key_verifier(master_key: bytes) -> tuple[bytes, bytes]:
    """Create encrypted verifier data for checking future passphrases."""
    nonce = os.urandom(_GCM_IV_SIZE)
    ciphertext = AESGCM(master_key).encrypt(
        nonce,
        _VAULT_VERIFIER_PLAINTEXT,
        None,
    )
    return nonce, ciphertext


def verify_master_key(master_key: bytes, nonce: bytes, ciphertext: bytes) -> bool:
    """Return True only when the derived master key can decrypt the verifier."""
    try:
        plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, None)
    except InvalidTag:
        return False
    return plaintext == _VAULT_VERIFIER_PLAINTEXT


def get_session_key(token: str) -> bytes:
    """Return a cached vault session key if it is still valid."""
    with _sessions_lock:
        entry = active_vault_sessions.get(token)
        if entry is None:
            raise KeyError(token)
        master_key, created_at = entry
        if time.time() - created_at > SESSION_TTL_SECONDS:
            del active_vault_sessions[token]
            raise KeyError(token)
        return master_key


def set_session_key(token: str, master_key: bytes) -> None:
    """Store a vault session key and evict all expired entries."""
    now = time.time()
    with _sessions_lock:
        expired = [
            t
            for t, (_, created_at) in active_vault_sessions.items()
            if now - created_at > SESSION_TTL_SECONDS
        ]
        for t in expired:
            del active_vault_sessions[t]
        active_vault_sessions[token] = (master_key, now)


def delete_session_key(token: str) -> bool:
    """Remove a vault session. Returns True if it existed."""
    with _sessions_lock:
        return active_vault_sessions.pop(token, None) is not None


def encrypt_file(master_key: bytes, source_path: str, dest_path: str) -> bytes:
    """Encrypt a file on disk with AES-256-GCM and append the tag to the output."""
    source = Path(source_path)
    destination = Path(dest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    iv = os.urandom(_GCM_IV_SIZE)
    cipher = Cipher(algorithms.AES(master_key), modes.GCM(iv))
    encryptor = cipher.encryptor()

    with source.open("rb") as source_handle, destination.open("wb") as dest_handle:
        while True:
            chunk = source_handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            encrypted_chunk = encryptor.update(chunk)
            if encrypted_chunk:
                dest_handle.write(encrypted_chunk)

        final_chunk = encryptor.finalize()
        if final_chunk:
            dest_handle.write(final_chunk)

        dest_handle.write(encryptor.tag)

    return iv


def decrypt_file_stream(
    master_key: bytes, iv: bytes, encrypted_path: str
) -> Iterator[bytes]:
    """Yield decrypted chunks only after AES-GCM tag verification succeeds."""
    encrypted_file = Path(encrypted_path)
    file_size = encrypted_file.stat().st_size
    if file_size < _GCM_TAG_SIZE:
        raise ValueError("Encrypted file is too small to contain an auth tag")

    fd, verified_plaintext_path = tempfile.mkstemp(prefix="vault-verified-")
    os.close(fd)
    verified_plaintext = Path(verified_plaintext_path)

    with encrypted_file.open("rb") as handle:
        try:
            handle.seek(file_size - _GCM_TAG_SIZE)
            tag = handle.read(_GCM_TAG_SIZE)
            if len(tag) != _GCM_TAG_SIZE:
                raise ValueError("Encrypted file is missing an auth tag")

            handle.seek(0)
            cipher = Cipher(algorithms.AES(master_key), modes.GCM(iv, tag))
            decryptor = cipher.decryptor()

            remaining = file_size - _GCM_TAG_SIZE
            with verified_plaintext.open("wb") as output:
                while remaining > 0:
                    chunk = handle.read(min(_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    decrypted_chunk = decryptor.update(chunk)
                    if decrypted_chunk:
                        output.write(decrypted_chunk)

                final_chunk = decryptor.finalize()
                if final_chunk:
                    output.write(final_chunk)

            with verified_plaintext.open("rb") as output:
                while True:
                    chunk = output.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
        finally:
            verified_plaintext.unlink(missing_ok=True)
