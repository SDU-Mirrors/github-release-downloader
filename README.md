# github-release-downloader

A python script to download the latest GitHub Releases.

## Usage

```txt
usage: main.py [-h] [--repo-file REPO_FILE]
               [--base-dir BASE_DIR] [-v] [--clean-up]

optional arguments:
  -h, --help            show this help message and exit
  --repo-file REPO_FILE
                        the path to a repo file
  --base-dir BASE_DIR   the path to the base dir
  -v, --version         show the version and exit
  --clean-up            whether to delete old artifacts or not
```

### Specify a GitHub credential
Set the environment variable `HTTP_BASIC_AUTH` in the form of `username:token`.

See also [personal access tokens](https://docs.github.com/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token).
Generally, you should only grant the `public_repo` access to the token. 

### Use http proxy
Set the environment variable `HTTP_PROXY` to an HTTP proxy.

Note: [A certain bug of Python](https://github.com/python/cpython/issues/66897) might cause issues with HTTP proxies, which was later fixed in Python 3.12.

### Last sync status

After each run, the downloader writes `lastsync.txt` under the `current` directory
(for the default settings, `./srv/current/lastsync.txt`). Each line records the
repository, the last successful sync time in Beijing time (UTC+08:00), and the
latest release tag:

```txt
repository | last_sync_at | version
texstudio-org/texstudio | 2026-09-12T16:00:00+08:00 | v4.8.1
```

The timestamp is updated after a repository finishes successfully, even when no
asset changes were needed. Failed repositories keep their previous record, while
repositories removed from `repos.yaml` are removed from the status file.

## License

MIT
