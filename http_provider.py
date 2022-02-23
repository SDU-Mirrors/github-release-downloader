import contextlib
import logging
from typing import Optional, Any
import urllib3
from urllib3 import PoolManager, HTTPResponse

from constant import UA_NAME

http: PoolManager = PoolManager(
    retries=False,
    timeout=urllib3.util.Timeout(connect=9, read=120),
    block=True,
)
chunk_size = 1048576


@contextlib.contextmanager
def urllib3_http_request(http: urllib3.PoolManager, *args: Any, **kwargs: Any):
    r = http.request(*args, **kwargs)
    try:
        yield r
    finally:
        r.release_conn()


def download_file(url: str, filepath: str, filesize: Optional[int] = None):
    logging.info('Downloading file {}'.format(url))
    with urllib3_http_request(http, 'GET', url, preload_content=False, headers={'User-Agent': UA_NAME}) as r:
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
