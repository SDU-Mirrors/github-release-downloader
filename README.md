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
Set the environment variable `HTTP_PROXY` to an http proxy.

Note: [A certain bug of Python]([https://bugs.python.org/issue22708](https://github.com/python/cpython/issues/66897)) might cause issues with proxies. [This PR](https://github.com/python/cpython/pull/8305) fixes the bug but it has not been merged yet.

## License

MIT
