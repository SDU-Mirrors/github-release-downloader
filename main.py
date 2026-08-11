#!/usr/bin/env python3

import argparse
import logging
import pathlib
import shutil
import yaml
from dataclasses import dataclass

from github import Repo, github_api_headers
from http_provider import download_file_with_retry, format_exception_chain
from constant import FULL_NAME, VERSION, REPO_URL


@dataclass
class RepoFailure:
    repo: Repo
    stage: str
    error: Exception


def format_exception(e):
    return format_exception_chain(e)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    arg = argparse.ArgumentParser()
    arg.add_argument('--repo-file', dest='repo_file', default='./repos.yaml', type=str, help='the path to a repo file')
    arg.add_argument('--base-dir', dest='base_dir', default='./srv', type=str, help='the path to the base dir')
    arg.add_argument('-v', '--version', dest='version', action="store_true", help='show the version and exits')
    arg.add_argument('--clean-up', dest='clean_up', action="store_true", help='whether to delete old artifacts or not')
    args = arg.parse_args()
    if args.version:
        print(FULL_NAME)
        print(VERSION)
        print(REPO_URL)
        exit()

    repo_file = args.repo_file
    base_dir = args.base_dir
    current_dir = base_dir + '/current'
    incoming_dir = base_dir + '/incoming'
    clean_up = args.clean_up

    with open(repo_file, "r") as stream:
        repo_yaml = yaml.safe_load(stream)

    repos = []

    for repo_str in repo_yaml['repos']:
        try:
            repo = Repo.parse_repo(repo_str)
            repos.append(repo)
        except Exception as e:
            logging.warning('Skipping invalid repo entry {}: {}'.format(repo_str, format_exception(e)))
            continue

    print('{} repos are being tracked, as follows:'.format(len(repos)))
    for repo in repos:
        print(repo)

    repos_succeed = []
    repos_skipped = []
    repos_failed = []
    for repo in repos:
        stage = 'initializing'
        try:
            repo_current_dir = current_dir + '/' + repo.owner + '_' + repo.repo

            stage = 'fetching repo information'
            repo_info_str = repo.get_repo_info()

            stage = 'fetching latest release'
            artifacts = repo.get_latest_artifacts()
            artifact_current_dir = current_dir + '/' + repo.owner + '_' + repo.repo + '/' + artifacts.tag_name
            if pathlib.Path(artifact_current_dir).exists():
                logging.info('Repo {} with tag {} already exists. Skip.'.format(repo, artifacts.tag_name))
                repos_skipped.append(repo)
                continue

            logging.info('Update available: {} -> {} ({} assets)'.format(
                repo, artifacts.tag_name, len(artifacts.artifacts)))

            stage = 'creating incoming directory'
            artifact_incoming_dir = incoming_dir + '/' + repo.owner + '_' + repo.repo + '/' + artifacts.tag_name
            pathlib.Path(artifact_incoming_dir).mkdir(parents=True, exist_ok=True)

            # download artifacts
            for artifact in artifacts.artifacts:
                stage = 'downloading asset {}'.format(artifact.name)
                artifact_filepath = artifact_incoming_dir + '/' + artifact.name
                logging.info('Downloading asset: {} {} {} ({} bytes)'.format(
                    repo, artifacts.tag_name, artifact.name, artifact.size))
                download_file_with_retry(
                    artifact.url,
                    artifact_filepath,
                    artifact.size,
                    headers=github_api_headers('application/octet-stream'),
                )

            # write readme file
            stage = 'writing readme'
            with open(artifact_incoming_dir + '/' + 'readme.txt', 'w') as stream:
                stream.write(repo_info_str)

            # clean up old versions
            if clean_up:
                stage = 'cleaning old versions'
                if pathlib.Path(repo_current_dir).exists():
                    shutil.rmtree(repo_current_dir)

            stage = 'moving incoming artifacts into current directory'
            pathlib.Path(repo_current_dir).mkdir(parents=True, exist_ok=True)
            shutil.move(artifact_incoming_dir, repo_current_dir)

            repos_succeed.append(repo)
        except Exception as e:
            failure = RepoFailure(repo, stage, e)
            repos_failed.append(failure)
            logging.exception('Repo {} failed while {}: {}'.format(
                repo, stage, format_exception(e)))

    print('Summary: {} success, {} skipped, {} failed.'.format(
        len(repos_succeed), len(repos_skipped), len(repos_failed)))
    for repo in repos_succeed:
        print('success - {}'.format(repo))
    for repo in repos_skipped:
        print('skipped - {}'.format(repo))
    for failure in repos_failed:
        print('failed - {} | stage: {} | error: {}'.format(
            failure.repo, failure.stage, format_exception(failure.error)))
