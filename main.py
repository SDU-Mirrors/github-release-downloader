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
from release_sync import (
    build_manifest,
    load_manifest,
    manifests_match,
    sync_release_assets,
    write_manifest_atomic,
)


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
    state_dir = base_dir + '/.state'
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
            repo_key = repo.owner + '_' + repo.repo
            repo_current_dir = pathlib.Path(current_dir) / repo_key

            stage = 'fetching repo information'
            repo_info_str = repo.get_repo_info()

            stage = 'fetching latest release'
            artifacts = repo.get_latest_artifacts()
            artifact_current_dir = repo_current_dir / artifacts.tag_name
            is_new_release = not artifact_current_dir.exists()
            manifest_path = pathlib.Path(state_dir) / repo_key / '{}.json'.format(artifacts.release_id)

            stage = 'loading release manifest'
            manifest = load_manifest(manifest_path)

            repo_incoming_dir = pathlib.Path(incoming_dir) / repo_key
            part_dir = repo_incoming_dir / '.parts' / str(artifacts.release_id)
            if is_new_release:
                sync_destination_dir = repo_incoming_dir / '.releases' / str(artifacts.release_id)
            else:
                sync_destination_dir = artifact_current_dir

            stage = 'reconciling release assets'
            logging.info('Reconciling release: {} {} ({} assets)'.format(
                repo, artifacts.tag_name, len(artifacts.artifacts)))
            stats = sync_release_assets(
                artifacts,
                sync_destination_dir,
                part_dir,
                manifest,
                download_file_with_retry,
                headers=github_api_headers('application/octet-stream'),
            )

            # write readme file
            stage = 'writing readme'
            readme_path = sync_destination_dir / 'readme.txt'
            if is_new_release or not readme_path.exists():
                with readme_path.open('w') as stream:
                    stream.write(repo_info_str)

            if is_new_release:
                # clean up old versions
                if clean_up:
                    stage = 'cleaning old versions'
                    if repo_current_dir.exists():
                        shutil.rmtree(repo_current_dir)

                stage = 'moving incoming artifacts into current directory'
                artifact_current_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(sync_destination_dir), str(artifact_current_dir))

            stage = 'writing release manifest'
            new_manifest = build_manifest(str(repo), artifacts)
            if not manifests_match(manifest, new_manifest):
                write_manifest_atomic(manifest_path, new_manifest)

            logging.info(
                'Release sync result: {} {} | added: {}, modified: {}, unchanged: {}, preserved: {}'.format(
                    repo,
                    artifacts.tag_name,
                    stats.added,
                    stats.modified,
                    stats.unchanged,
                    stats.preserved,
                ))

            if is_new_release or stats.changed:
                repos_succeed.append(repo)
            else:
                repos_skipped.append(repo)
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
