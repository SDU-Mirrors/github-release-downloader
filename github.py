from __future__ import annotations

import logging
import os
import re
import json
from typing import Dict, List, Optional, Any
from urllib3 import HTTPResponse
from http_provider import http, check_http_code, redirect_statuses, max_redirects
from constant import UA_NAME, FULL_NAME, REPO_URL


def github_api_headers(accept: str = 'application/vnd.github.v3+json') -> Dict[str, str]:
    headers = {
        'Accept': accept,
        'User-Agent': UA_NAME,
    }
    github_token = os.getenv('GITHUB_TOKEN')
    if github_token:
        headers['Authorization'] = 'Bearer {}'.format(github_token)
    return headers


def github_api_get_json(url: str) -> Any:
    resp = None
    for redirect_count in range(max_redirects):
        logging.debug('GET {}'.format(url))
        resp: HTTPResponse = http.request(
            'GET',
            url,
            headers=github_api_headers(),
            redirect=False,
        )
        if resp.status not in redirect_statuses:
            break

        redirect_url = resp.headers.get('Location')
        if redirect_url is None:
            try:
                redirect_url = json.loads(resp.data).get('url')
            except Exception:
                redirect_url = None
        if redirect_url is None:
            break

        logging.debug('GitHub API redirected from {} to {}'.format(url, redirect_url))
        resp.release_conn()
        url = redirect_url
    else:
        raise Exception('Too many redirects while fetching GitHub API url {}'.format(url))

    check_http_code(resp, url)
    try:
        return json.loads(resp.data)
    except json.JSONDecodeError as e:
        raise Exception('Invalid JSON response from {}'.format(url)) from e


class Artifacts:
    def __init__(self, release_id: int, tag_name: str, artifacts: List[Artifact]):
        self.release_id = release_id
        self.tag_name = tag_name
        self.artifacts = artifacts


class Artifact:
    def __init__(
        self,
        asset_id: int,
        name: str,
        url: str,
        size: Optional[int] = None,
        updated_at: Optional[str] = None,
        digest: Optional[str] = None,
    ):
        self.id = asset_id
        self.name = name
        self.url = url
        self.size = size
        self.updated_at = updated_at
        self.digest = digest


class Repo:
    def __init__(self, owner: str, repo: str):
        self.owner = owner
        self.repo = repo

    def __str__(self):
        return '{}/{}'.format(self.owner, self.repo)

    @staticmethod
    def parse_repo(repo_str: str) -> Repo:
        if not re.fullmatch(r'[A-Za-z\d_.\-]+/[A-Za-z\d_.\-]+', repo_str):
            raise Exception('Invalid repo format for string {}'.format(repo_str))
        result = repo_str.split('/')
        assert len(result) == 2
        return Repo(result[0], result[1])

    def get_repo_info(self) -> str:
        logging.debug('Fetching information of repo {}/{}'.format(self.owner, self.repo))
        url = 'https://api.github.com/repos/{}/{}'.format(self.owner, self.repo)
        resp_json = github_api_get_json(url)

        ret = 'This site distributes {}'.format(resp_json['full_name'])
        if resp_json['license'] is not None and resp_json['license']['url'] is not None:
            ret += ' under the terms of {}. '.format(resp_json['license']['name'])
        else:
            ret += '. '
        ret += 'The source code is available at {}. '.format(resp_json['html_url'])
        ret += 'This mirror is powered by {}, at {}.'.format(FULL_NAME, REPO_URL)
        return ret

    def get_latest_artifacts(self) -> Artifacts:
        logging.debug('Fetching latest release of repo {}/{}'.format(self.owner, self.repo))
        url = 'https://api.github.com/repos/{}/{}/releases/latest'.format(self.owner, self.repo)
        resp_json = github_api_get_json(url)
        release_id = resp_json['id']
        tag_name = resp_json['tag_name']
        assets = resp_json['assets']
        logging.debug('{} assets available in repo {}/{} tag {}'.format(
            len(assets), self.owner, self.repo, tag_name))

        ret_artifacts = []
        for asset in assets:
            asset_id = asset['id']
            asset_name = asset['name']
            asset_url = asset['url']
            asset_size = asset['size']
            asset_updated_at = asset.get('updated_at')
            asset_digest = asset.get('digest')
            ret_artifacts.append(Artifact(
                asset_id,
                asset_name,
                asset_url,
                asset_size,
                asset_updated_at,
                asset_digest,
            ))

        return Artifacts(release_id, tag_name, ret_artifacts)
