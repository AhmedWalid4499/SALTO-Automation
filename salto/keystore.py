"""Encrypt small secrets (the Claude API key) with Windows DPAPI.

The encrypted value can only be decrypted by the same Windows user on the same
machine, so the key never sits in plain text in config.json.
"""
import base64
import ctypes
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _out(blob):
    data = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return data


def protect(text: str) -> str:
    if not text:
        return ""
    src, _keep = _blob(text.encode("utf-8"))
    dst = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "SALTO Buddy", None, None, None, 0,
                                                  ctypes.byref(dst)):
        raise OSError("CryptProtectData failed")
    return base64.b64encode(_out(dst)).decode("ascii")


def unprotect(token: str) -> str:
    if not token:
        return ""
    try:
        src, _keep = _blob(base64.b64decode(token))
    except ValueError:  # damaged in config.json: treat as not set
        return ""
    dst = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0,
                                                    ctypes.byref(dst)):
        return ""  # different user/machine: treat as not set
    try:
        return _out(dst).decode("utf-8")
    except UnicodeDecodeError:
        return ""
