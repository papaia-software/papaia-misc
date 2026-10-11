"""Public HTTP only: DNS validation and IP pinning on every redirect, no proxy inheritance."""
import ipaddress
import socket
import time
from collections import OrderedDict
from threading import Lock
from urllib.parse import urlsplit, urlunsplit, urljoin
import httpx
from .schemas import public_url
from .config import settings

class SourceError(Exception):
    pass

def resolve_public(host):
    try:
        addresses = sorted({x[4][0] for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
    except socket.gaierror as exc:
        raise SourceError('Não foi possível resolver o domínio') from exc
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise SourceError('Acesso a endereços privados, locais ou reservados bloqueado')
    return addresses[0]

def _fetch_public_uncached(url, allowed_origin=None):
    for redirect in range(4):
        try:
            public_url(url)
        except ValueError as exc:
            raise SourceError(str(exc)) from exc
        parsed = urlsplit(url)
        if allowed_origin is not None and parsed.netloc.lower()!=allowed_origin.lower():
            raise SourceError('Redirecionamento entre domínios requer recadastro da fonte')
        ip = resolve_public(parsed.hostname)
        address = f'[{ip}]' if ':' in ip else ip
        pinned = urlunsplit((parsed.scheme,address,parsed.path or '/',parsed.query,''))
        for attempt in range(3):
            try:
                with httpx.Client(timeout=20,trust_env=False,follow_redirects=False) as client:
                    with client.stream('GET',pinned,headers={'Host':parsed.netloc,'User-Agent':'PapaiaMisc/0.1 (+internal market research)'},extensions={'sni_hostname':parsed.hostname}) as response:
                        if response.status_code in (301,302,303,307,308):
                            url = urljoin(url,response.headers.get('location',''))
                            break
                        if response.status_code in (429,500,502,503,504) and attempt < 2:
                            time.sleep(0.5 * 2**attempt)
                            continue
                        response.raise_for_status()
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > settings().fetch_max_bytes:
                                raise SourceError('Fonte excede limite de 2 MB')
                            chunks.append(chunk)
                        return b''.join(chunks), url
            except httpx.HTTPError as exc:
                if attempt < 2:
                    time.sleep(0.5 * 2**attempt)
                    continue
                raise SourceError('Falha HTTP ao acessar fonte pública') from exc
        else:
            raise SourceError('Não foi possível coletar a fonte')
    raise SourceError('Limite de redirecionamentos excedido')


# Bounded process-local cache. Only successful public bytes are stored, never credentials.
_CACHE = OrderedDict()
_CACHE_LOCK = Lock()

def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()

def fetch_public(url, allowed_origin=None, cache_ttl=300):
    try:
        public_url(url)
    except ValueError as exc:
        raise SourceError(str(exc)) from exc
    if allowed_origin is not None and urlsplit(url).netloc.lower()!=allowed_origin.lower():
        raise SourceError('Domínio não corresponde à fonte permitida')
    key=(url,allowed_origin)
    with _CACHE_LOCK:
        cached=_CACHE.get(key)
        if cached and time.monotonic()-cached[0]<cache_ttl:
            _CACHE.move_to_end(key)
            return cached[1]
        _CACHE.pop(key,None)
    result=_fetch_public_uncached(url,allowed_origin)
    if cache_ttl>0:
        with _CACHE_LOCK:
            _CACHE[key]=(time.monotonic(),result)
            _CACHE.move_to_end(key)
            while len(_CACHE)>16:
                _CACHE.popitem(last=False)
    return result
