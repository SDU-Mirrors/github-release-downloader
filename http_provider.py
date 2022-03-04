import contextlib
import logging
from typing import Optional, Any
import urllib3
from urllib3 import PoolManager, HTTPResponse, ProxyManager
from urllib.request import getproxies

from constant import UA_NAME

logger = logging.getLogger(__name__)

http: PoolManager = PoolManager()
chunk_size = 1048576


def get_proxy() -> Optional[str]:
    proxies = getproxies()
    if 'all' in proxies.keys():
        return proxies['all']
    if 'http' in proxies.keys():
        return proxies['http']
    return None


def initialize():
    global http
    proxy = get_proxy()
    if proxy is None:
        http = PoolManager(
            retries=False,
            timeout=urllib3.util.Timeout(connect=9, read=120),
            block=True,
        )
    else:
        logger.info('Proxy server is set to {}.'.format(proxy))
        http = ProxyManager(
            proxy_url=proxy,
            retries=False,
            timeout=urllib3.util.Timeout(connect=9, read=120),
            block=True,
        )


initialize()


@contextlib.contextmanager
def urllib3_http_request(http: urllib3.PoolManager, *args: Any, **kwargs: Any):
    r = http.request(*args, **kwargs)
    try:
        yield r
    finally:
        r.release_conn()


def download_file(url: str, filepath: str, filesize: Optional[int] = None):
    logger.info('Downloading file {}'.format(url))
    with urllib3_http_request(http, 'GET', url, preload_content=False, headers={'User-Agent': UA_NAME}) as r:
        with open(filepath, 'wb') as f:
            content_len = int(r.headers['Content-length'])
            downloaded_size = 0
            logger.info('Connecting...')
            for chunk in r.stream(chunk_size):
                downloaded_size += len(chunk)
                f.write(chunk)
                logger.info('{:.2f}/{:.2f} MiB, {:.2%}'.format(
                    downloaded_size / 1048576, content_len / 1048576,
                    downloaded_size / content_len),
                )
        check_http_code(r, url)
        if filesize is not None and filesize != downloaded_size:
            raise Exception('File length mismatch. Got {}, but {} is expected.'.format(downloaded_size, filesize))


def download_file_with_retry(url: str, filepath: str, filesize: Optional[int] = None, retry_time: int = 3):
    for i in range(retry_time):
        try:
            download_file(url, filepath, filesize)
            break
        except Exception as e:
            logger.warning(e)
            if i == retry_time - 1:  # is last loop
                raise e


def check_http_code(resp: HTTPResponse, url: str):
    if resp.status != 200:
        raise Exception('HTTP {} on url {}'.format(resp.status, url))
