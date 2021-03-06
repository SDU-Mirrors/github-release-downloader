#!/usr/bin/env python3

import argparse
import logging
import pathlib
import shutil
import yaml
import os

import github
from github import Repo
from http_provider import download_file_with_retry
from constant import FULL_NAME, VERSION, REPO_URL, UA_NAME

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    arg = argparse.ArgumentParser()
    arg.add_argument('--repo-file', dest='repo_file', default='./repos.yaml', type=str, help='the path to a repo file')
    arg.add_argument('--base-dir', dest='base_dir', default='./srv', type=str, help='the path to the base dir')
    arg.add_argument('-v', '--version', dest='version', action="store_true", help='show the version and exit')
    arg.add_argument('--clean-up', dest='clean_up', action="store_true", help='whether to delete old artifacts or not')
    args = arg.parse_args()
    if args.version:
        print(FULL_NAME)
        print(VERSION)
        print(REPO_URL)
        exit()

    # Load options for GitHub API
    github_option = github.APIOption()
    github_option.basic_auth = os.environ.get('HTTP_BASIC_AUTH', None)
    github_option.user_agent = UA_NAME
    if not github_option.basic_auth:
        logging.warning('No credentials found. Please specify a credential via HTTP_BASIC_AUTH environment.')
    else:
        logging.info('Successfully loaded the GitHub API credential.')

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
            logging.warning(e)
            continue

    print('{} repos will be downloaded, as follows:'.format(len(repos)))
    for repo in repos:
        print(repo)

    repos_succeed = []
    repos_skipped = []
    repos_failed = []
    for repo in repos:
        try:
            repo_current_dir = current_dir + '/' + repo.owner + '_' + repo.repo

            repo_info_str = repo.get_repo_info(github_option)

            artifacts = repo.get_latest_artifacts(github_option)
            artifact_current_dir = current_dir + '/' + repo.owner + '_' + repo.repo + '/' + artifacts.tag_name
            if pathlib.Path(artifact_current_dir).exists():
                logging.info('Repo {} with tag {} already exists. Skip.'.format(repo, artifacts.tag_name))
                repos_skipped.append(repo)
                continue

            artifact_incoming_dir = incoming_dir + '/' + repo.owner + '_' + repo.repo + '/' + artifacts.tag_name
            pathlib.Path(artifact_incoming_dir).mkdir(parents=True, exist_ok=True)

            # download artifacts
            for artifact in artifacts.artifacts:
                artifact_filepath = artifact_incoming_dir + '/' + artifact.name
                download_file_with_retry(artifact.url, artifact_filepath, artifact.size)

            # write readme file
            with open(artifact_incoming_dir + '/' + 'readme.txt', 'w') as stream:
                stream.write(repo_info_str)

            # clean up old versions
            if clean_up:
                if pathlib.Path(repo_current_dir).exists():
                    shutil.rmtree(repo_current_dir)

            pathlib.Path(repo_current_dir).mkdir(parents=True, exist_ok=True)
            shutil.move(artifact_incoming_dir, repo_current_dir)

            repos_succeed.append(repo)
        except Exception as e:
            repos_failed.append(repo)
            logging.warning(e)

    print('Summary: {} success, {} skipped, {} failed.'.format(
        len(repos_succeed), len(repos_skipped), len(repos_failed)))
    for repo in repos_succeed:
        print('success - {}'.format(repo))
    for repo in repos_skipped:
        print('skipped - {}'.format(repo))
    for repo in repos_failed:
        print('failed - {}'.format(repo))
