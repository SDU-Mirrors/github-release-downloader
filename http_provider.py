import contextlib
import logging
from typing import Optional, Any, Dict, Set, Union
import urllib3
from urllib3 import HTTPResponse
from urllib.parse import urlparse

from urllib3.exceptions import HostChangedError

from constant import UA_NAME

Pool = Union[urllib3.HTTPSConnectionPool, urllib3.PoolManager]

http: Pool = urllib3.PoolManager(
    retries=False,
    timeout=urllib3.util.Timeout(connect=9, read=120),
    block=True,
)
chunk_size = 1048576

custom_sni_pools: Dict[str, Pool] = {}
no_sni_domains: Set[str] = {'api.github.com', 'github.com'}


def new_no_sni_pool(domain: str) -> Pool:
    return urllib3.HTTPSConnectionPool(domain, server_hostname=None, assert_hostname=domain)


def get_no_sni_pool(domain: str) -> Pool:
    if domain not in custom_sni_pools:
        custom_sni_pools[domain] = new_no_sni_pool(domain)
    return custom_sni_pools[domain]


def urllib3_http_request_auto(method, url, **kwargs):
    domain = urlparse(url).netloc

    kwargs['assert_same_host'] = True
    headers = kwargs.get('headers', dict())
    headers['Host'] = domain
    kwargs['headers'] = headers

    if domain in no_sni_domains:
        pool = get_no_sni_pool(domain)
        logging.debug('use no-sni pool')
    else:
        pool = http
        logging.debug('use normal pool')

    try:
        r = pool.request(method, url, **kwargs)
    except HostChangedError as e:
        logging.info('Redirect to {}'.format(e.url))
        # TODO deal with infinite loop
        url = e.url
        r = urllib3_http_request_auto(method, url, **kwargs)
    return r


@contextlib.contextmanager
def urllib3_http_request_auto_managed(*args: Any, **kwargs: Any):
    r = urllib3_http_request_auto(*args, **kwargs)
    try:
        yield r
    finally:
        r.release_conn()


def download_file(url: str, filepath: str, filesize: Optional[int] = None):
    logging.info('Downloading file {}'.format(url))
    with urllib3_http_request_auto_managed('GET', url, preload_content=False, headers={'User-Agent': UA_NAME}) as r:
        with open(filepath, 'wb') as f:
            content_len = int(r.headers['Content-length'])
            downloaded_size = 0
            logging.info('Connecting...')
            for chunk in r.stream(chunk_size):
                downloaded_size += len(chunk)
                f.write(chunk)
                logging.info('{:.2f}/{:.2f} MiB, {:.2%}'.format(
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
            logging.warning(e)
            if i == retry_time - 1:  # is last loop
                raise e


def check_http_code(resp: HTTPResponse, url: str):
    if resp.status != 200:
        raise Exception('HTTP {} on url {}'.format(resp.status, url))
