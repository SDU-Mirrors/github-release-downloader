from __future__ import annotations

import logging
import re
import json
from typing import List, Optional
from urllib3 import HTTPResponse
from http_provider import http, check_http_code


class Artifacts:
    def __init__(self, tag_name: str, artifacts: List[Artifact]):
        self.tag_name = tag_name
        self.artifacts = artifacts


class Artifact:
    def __init__(self, name: str, url: str, size: Optional[int] = None):
        self.name = name
        self.url = url
        self.size = size


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

    def get_latest_artifacts(self) -> Artifacts:
        logging.info('Fetching latest release of repo {}/{}'.format(self.owner, self.repo))
        url = 'https://api.github.com/repos/{}/{}/releases/latest'.format(self.owner, self.repo)
        resp: HTTPResponse = http.request(
            'GET',
            url,
            headers={
                'Accept': 'application/vnd.github.v3+json',
            }
        )
        check_http_code(resp, url)

        resp_json = json.loads(resp.data)
        tag_name = resp_json['tag_name']
        assets = resp_json['assets']
        logging.info('{} asserts available in repo {}/{}'.format(len(assets), self.owner, self.repo))

        ret_artifacts = []
        for asset in assets:
            asset_name = asset['name']
            asset_url = asset['browser_download_url']
            asset_size = asset['size']
            ret_artifacts.append(Artifact(asset_name, asset_url, asset_size))

        return Artifacts(tag_name, ret_artifacts)
