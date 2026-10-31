"""Local Tesseract C API; no subprocess, model download, or cloud request at runtime."""
import ctypes as C
import ctypes.util
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import zxingcpp

# Where Homebrew (Apple Silicon) and the UB Mannheim installer (Windows) put the library; find_library misses both
KNOWN=['/opt/homebrew/lib/libtesseract.dylib',r'C:\Program Files\Tesseract-OCR\libtesseract-5.dll']

def qr_hosts(im):
    """Hostnames of web links in the image's QR codes (a QR is a link the reader cannot see); never the path or query."""
    hosts=[]
    for code in zxingcpp.read_barcodes(im,formats=zxingcpp.BarcodeFormat.QRCode):
        parts=urlsplit(code.text.strip())
        if parts.scheme in ('http','https') and parts.hostname and parts.hostname not in hosts:hosts.append(parts.hostname)
    return hosts[:5]

class OCR:
    def __init__(self, data=None):
        name=ctypes.util.find_library('tesseract') or next((p for p in KNOWN if Path(p).exists()),None)
        if not name: raise RuntimeError('Local libtesseract is not installed')
        self.lib=C.CDLL(name)
        signatures={
            'TessBaseAPICreate':([],C.c_void_p),
            'TessBaseAPIInit3':([C.c_void_p,C.c_char_p,C.c_char_p],C.c_int),
            'TessBaseAPISetImage':([C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int],None),
            'TessBaseAPIGetUTF8Text':([C.c_void_p],C.c_void_p),
            'TessBaseAPIMeanTextConf':([C.c_void_p],C.c_int),
            'TessBaseAPISetPageSegMode':([C.c_void_p,C.c_int],None),
            'TessBaseAPIClear':([C.c_void_p],None),
            'TessDeleteText':([C.c_void_p],None),
            'TessBaseAPIDelete':([C.c_void_p],None),
        }
        for key,(args,result) in signatures.items():
            f=getattr(self.lib,key);f.argtypes=args;f.restype=result
        self.handle=self.lib.TessBaseAPICreate()
        path=Path(data or Path(__file__).parent/'models/ocr')
        if self.lib.TessBaseAPIInit3(self.handle,str(path).encode(),b'ces'):
            self.close();raise RuntimeError('Czech OCR model is missing')
        self.lib.TessBaseAPISetPageSegMode(self.handle,6)
    def read(self,raw):
        from PIL import Image,ImageOps
        Image.MAX_IMAGE_PIXELS=6_000_000
        with Image.open(BytesIO(raw)) as source:
            if source.width*source.height>6_000_000: raise ValueError('Image too large')
            im=ImageOps.exif_transpose(source).convert('RGB')
            im.thumbnail((1800,1800))
        buf=C.create_string_buffer(im.tobytes())
        self.lib.TessBaseAPISetImage(self.handle,buf,im.width,im.height,3,im.width*3)
        ptr=self.lib.TessBaseAPIGetUTF8Text(self.handle)
        try: text=C.string_at(ptr).decode('utf-8') if ptr else ''
        finally:
            if ptr:self.lib.TessDeleteText(ptr)
        confidence=self.lib.TessBaseAPIMeanTextConf(self.handle)
        self.lib.TessBaseAPIClear(self.handle)
        return {'text':text.strip(),'ocr_confidence':confidence,'links':qr_hosts(im)}
    def close(self):
        if self.handle:self.lib.TessBaseAPIDelete(self.handle);self.handle=None
    def __del__(self):
        try:self.close()
        except Exception:pass
