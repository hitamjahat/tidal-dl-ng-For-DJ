"""AES decryption helpers for TIDAL stream and file protection.

This module implements the legacy TIDAL DRM scheme used for encrypted
audio streams. ``decrypt_security_token`` turns the Base64-wrapped
security token from the stream manifest into the AES key and nonce, and
``decrypt_file`` applies AES-CTR to recover the plaintext audio.
"""

import base64
import pathlib
from typing import TYPE_CHECKING

from Crypto.Cipher import AES
from Crypto.Util import Counter

if TYPE_CHECKING:
    from Crypto.Cipher._mode_cbc import CbcMode
    from Crypto.Cipher._mode_ctr import CtrMode


def _new_cbc_cipher(key: bytes, iv: bytes) -> "CbcMode":
    """Create an AES-CBC cipher in CBC mode.

    Args:
        key (bytes): AES secret key.
        iv (bytes): Initialization vector.

    Returns:
        CbcMode: Configured CBC decryptor.
    """
    return AES.new(key, AES.MODE_CBC, iv=iv, use_aesni=False)


def _new_ctr_cipher(
    key: bytes,
    counter: dict[str, int | bytes | bool],
) -> "CtrMode":
    """Create an AES-CTR cipher in CTR mode.

    Args:
        key (bytes): AES secret key.
        counter (dict[str, int | bytes | bool]): CTR state dictionary.

    Returns:
        CtrMode: Configured CTR decryptor.
    """
    return AES.new(
        key,
        AES.MODE_CTR,
        counter=counter,
        use_aesni=False,
    )


def decrypt_security_token(
    security_token: str,
) -> tuple[bytes, bytes]:
    """Decrypt a security token into an AES key and nonce.

    The token is AES-CBC encrypted with a fixed master key. The first
    16 bytes are the IV; the remainder is the ciphertext. After
    decryption the first 16 bytes are the stream key and the following
    8 bytes are the CTR nonce.

    Args:
        security_token (str): Base64-encoded token from the stream
            manifest's ``securityToken`` field.

    Returns:
        tuple[bytes, bytes]: The decryption key and nonce.
    """
    # Do not change this: fixed master key for the legacy DRM scheme.
    master_key_b64 = "UIlTTEMmmLfGowo/UC60x2H45W6MdGgTRfo/umg4754="

    # Decode the base64 strings to raw bytes.
    master_key = base64.b64decode(master_key_b64)
    token_bytes = base64.b64decode(security_token)

    # Get the IV from the first 16 bytes of the security token.
    iv = token_bytes[:16]
    encrypted_st = token_bytes[16:]

    # Initialize decryptor.
    decryptor = _new_cbc_cipher(master_key, iv)

    # Decrypt the security token.
    decrypted_st = decryptor.decrypt(encrypted_st)

    # Get the audio stream decryption key and nonce from the result.
    key = decrypted_st[:16]
    nonce = decrypted_st[16:24]

    return key, nonce


def decrypt_file(
    path_file_encrypted: pathlib.Path,
    path_file_destination: pathlib.Path,
    key: bytes,
    nonce: bytes,
) -> None:
    """Decrypt an encrypted audio file using AES-CTR.

    Args:
        path_file_encrypted (Path): Source encrypted file.
        path_file_destination (Path): Target path for plaintext output.
        key (bytes): AES key from ``decrypt_security_token``.
        nonce (bytes): CTR prefix from ``decrypt_security_token``.

    TODO: Confirm whether this is MQA-only or applies to all formats.
    """
    # Initialize counter and file decryptor.
    counter = Counter.new(64, prefix=nonce, initial_value=0)
    decryptor = _new_ctr_cipher(key, counter)

    # Open and decrypt.
    with path_file_encrypted.open("rb") as f_src:
        audio_decrypted = decryptor.decrypt(f_src.read())

        # Replace with decrypted file.
        with path_file_destination.open("wb") as f_dst:
            f_dst.write(audio_decrypted)
