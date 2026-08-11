import contextlib
import logging
from typing import Dict, Optional, Any
from urllib.parse import urljoin, urlparse
import urllib3
from urllib3 import PoolManager, HTTPResponse

http: PoolManager = PoolManager(
    retries=False,
    timeout=urllib3.util.Timeout(connect=9, read=120),
    block=True,
)
chunk_size = 1048576
redirect_statuses = (301, 302, 303, 307, 308)
max_redirects = 6


def _format_exception(e: Exception) -> str:
    return '{}: {}'.format(type(e).__name__, e)


def format_exception_chain(e: Exception) -> str:
    messages = []
    current = e
    while current is not None:
        messages.append(_format_exception(current))
        current = current.__cause__ or current.__context__
    return ' <- caused by: '.join(messages)


@contextlib.contextmanager
def urllib3_http_request(http: urllib3.PoolManager, *args: Any, **kwargs: Any):
    r = http.request(*args, **kwargs)
    try:
        yield r
    finally:
        r.release_conn()


def redirect_headers(
    headers: Optional[Dict[str, str]],
    original_url: str,
    redirect_url: str,
) -> Optional[Dict[str, str]]:
    if headers is None:
        return None

    original = urlparse(original_url)
    redirected = urlparse(redirect_url)
    if (original.scheme, original.netloc) == (redirected.scheme, redirected.netloc):
        return headers

    ret = dict(headers)
    ret.pop('Authorization', None)
    return ret


def download_file(
    url: str,
    filepath: str,
    filesize: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
):
    logging.debug('Downloading file {} -> {}'.format(url, filepath))
    original_url = url
    request_headers = headers
    r = None
    for redirect_count in range(max_redirects):
        r = http.request(
            'GET',
            url,
            headers=request_headers,
            preload_content=False,
            redirect=False,
        )
        if r.status not in redirect_statuses:
            break

        redirect_url = r.headers.get('Location')
        if redirect_url is None:
            check_http_code(r, url)
        r.release_conn()
        redirect_url = urljoin(url, redirect_url)
        logging.debug('Download redirected from {} to {}'.format(url, redirect_url))
        request_headers = redirect_headers(request_headers, url, redirect_url)
        url = redirect_url
    else:
        raise Exception('Too many redirects while downloading {} -> {}'.format(original_url, filepath))

    try:
        check_http_code(r, url)
        with open(filepath, 'wb') as f:
            content_len_header = r.headers.get('Content-length')
            if content_len_header is None:
                raise Exception('Missing Content-length header on url {}'.format(url))
            content_len = int(content_len_header)
            downloaded_size = 0
            logging.debug('Connecting...')
            for chunk in r.stream(chunk_size):
                downloaded_size += len(chunk)
                f.write(chunk)
                logging.debug('{:.2f}/{:.2f} MiB, {:.2%}'.format(
                    downloaded_size / 1048576, content_len / 1048576,
                    downloaded_size / content_len),
                )
        if filesize is not None and filesize != downloaded_size:
            raise Exception('File length mismatch on url {}. Got {}, but {} is expected. Filepath: {}'.format(
                url, downloaded_size, filesize, filepath))
    finally:
        if r is not None:
            r.release_conn()


def download_file_with_retry(
    url: str,
    filepath: str,
    filesize: Optional[int] = None,
    retry_time: int = 3,
    headers: Optional[Dict[str, str]] = None,
):
    for i in range(retry_time):
        try:
            download_file(url, filepath, filesize, headers)
            break
        except Exception as e:
            logging.warning('Download attempt {}/{} failed for {} -> {}: {}'.format(
                i + 1, retry_time, url, filepath, format_exception_chain(e)))
            if i == retry_time - 1:  # is last loop
                raise Exception('Download failed after {} attempts for {} -> {}'.format(
                    retry_time, url, filepath)) from e


def check_http_code(resp: HTTPResponse, url: str):
    if resp.status != 200:
        body_preview = ''
        if resp.data is not None:
            body_preview = resp.data[:500].decode('utf-8', errors='replace')
        rate_limit = resp.headers.get('X-RateLimit-Remaining')
        rate_limit_reset = resp.headers.get('X-RateLimit-Reset')
        location = resp.headers.get('Location')
        raise Exception(
            'HTTP {} on url {}. Location: {}. X-RateLimit-Remaining: {}. X-RateLimit-Reset: {}. Body: {}'.format(
                resp.status, url, location, rate_limit, rate_limit_reset, body_preview))
