import argparse
import logging
import pathlib
import shutil
import yaml

from github import Repo
from http_provider import download_file, download_file_with_retry

NAME = 'github-release-downloader'
VERSION = 'v0.1'

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    arg = argparse.ArgumentParser()
    arg.add_argument('--repo-file', dest='repo_file', default='./repos.yaml', type=str, help='the path to a repo file')
    arg.add_argument('--base-dir', dest='base_dir', default='./srv', type=str, help='the path to the base dir')
    arg.add_argument('-v', '--version', dest='version', action="store_true", help='standalone: show the version')
    args = arg.parse_args()
    if args.version:
        print(NAME)
        print(VERSION)
        exit()

    repo_file = args.repo_file
    base_dir = args.base_dir
    current_dir = base_dir + '/current'
    incoming_dir = base_dir + '/incoming'

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
            artifacts = repo.get_latest_artifacts()
            artifact_current_dir = current_dir + '/' + repo.owner + '_' + repo.repo + '/' + artifacts.tag_name
            if pathlib.Path(artifact_current_dir).exists():
                logging.info('Repo {} with tag {} already exists. Skip.'.format(repo, artifacts.tag_name))
                repos_skipped.append(repo)
                continue

            artifact_incoming_dir = incoming_dir + '/' + repo.owner + '_' + repo.repo + '/' + artifacts.tag_name
            pathlib.Path(artifact_incoming_dir).mkdir(parents=True, exist_ok=True)

            for artifact in artifacts.artifacts:
                artifact_filepath = artifact_incoming_dir + '/' + artifact.name
                download_file_with_retry(artifact.url, artifact_filepath, artifact.size)

            # if pathlib.Path(artifact_current_dir).exists():
            #     shutil.rmtree(artifact_current_dir)
            shutil.move(artifact_incoming_dir, artifact_current_dir)

            repos_succeed.append(repo)
        except Exception as e:
            repos_failed.append(repo)
            logging.warning(e)

    print('Summary: {} succeed, {} skipped, {} repos failed.'.format(
        len(repos_succeed), len(repos_skipped), len(repos_failed)))
    for repo in repos_succeed:
        print('success - {}'.format(repo))
    for repo in repos_skipped:
        print('skipped - {}'.format(repo))
    for repo in repos_failed:
        print('failed - {}'.format(repo))
