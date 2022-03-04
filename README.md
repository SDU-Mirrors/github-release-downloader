# github-release-downloader

A python script to download the latest GitHub Releases.

## Usage

```txt
usage: main.py [-h] [--repo-file REPO_FILE] [--base-dir BASE_DIR] [-v] [--clean-up]

options:
  -h, --help            show this help message and exit
  --repo-file REPO_FILE
                        the path to a repo file
  --base-dir BASE_DIR   the path to the base dir
  -v, --version         standalone: show the version
  --clean-up            whether to delete old artifacts or not
```

Note: [A certain bug of Python](https://bugs.python.org/issue22708) might causes issues with proxies. [This PR](https://github.com/python/cpython/pull/8305) fixes the bug but it has not been merged yet.

## License

MIT
