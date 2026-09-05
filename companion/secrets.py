"""Windows user-bound DPAPI, with an environment override for tests."""
import ctypes
import os
from pathlib import Path
from ctypes import wintypes


def data_dir():
    return Path(os.environ.get('CHANGZHENG_DATA_DIR') or (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Changzheng'))


class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def _crypt(value: bytes, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('非 Windows 请通过 SILICONFLOW_API_KEY 环境变量配置密钥')
    buf = ctypes.create_string_buffer(value)
    src = Blob(len(value), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(out)):
        raise RuntimeError('无法访问当前 Windows 用户的加密凭据')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def save_key(value: str):
    path = data_dir() / 'provider.key'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_crypt(value.strip().encode()))


def get_key():
    if os.environ.get('SILICONFLOW_API_KEY'):
        return os.environ['SILICONFLOW_API_KEY']
    path = data_dir() / 'provider.key'
    return _crypt(path.read_bytes(), decrypt=True).decode() if path.exists() else ''
