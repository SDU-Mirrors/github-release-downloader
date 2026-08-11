from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


manifest_schema_version = 1
hash_chunk_size = 1048576


@dataclass
class SyncStats:
    added: int = 0
    modified: int = 0
    unchanged: int = 0
    preserved: int = 0

    @property
    def changed(self) -> bool:
        return self.added > 0 or self.modified > 0


def manifest_asset(asset: Any) -> Dict[str, Any]:
    return {
        'id': asset.id,
        'name': asset.name,
        'size': asset.size,
        'updated_at': asset.updated_at,
        'digest': asset.digest,
    }


def build_manifest(repository: str, artifacts: Any) -> Dict[str, Any]:
    assets = [manifest_asset(asset) for asset in artifacts.artifacts]
    assets.sort(key=lambda asset: (str(asset['id']), asset['name']))
    return {
        'schema_version': manifest_schema_version,
        'repository': repository,
        'release_id': artifacts.release_id,
        'tag_name': artifacts.tag_name,
        'synced_at': datetime.now(timezone.utc).isoformat(),
        'assets': assets,
    }


def load_manifest(filepath: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not filepath.exists():
        return None

    try:
        with filepath.open('r', encoding='utf-8') as stream:
            manifest = json.load(stream)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.warning('Ignoring invalid release manifest {}: {}'.format(filepath, e))
        return None

    if not isinstance(manifest, dict):
        logging.warning('Ignoring release manifest with invalid root object in {}'.format(filepath))
        return None
    if manifest.get('schema_version') != manifest_schema_version:
        logging.warning('Ignoring unsupported release manifest schema in {}'.format(filepath))
        return None
    manifest_assets = manifest.get('assets')
    if not isinstance(manifest_assets, list) or not all(isinstance(asset, dict) for asset in manifest_assets):
        logging.warning('Ignoring release manifest with invalid assets in {}'.format(filepath))
        return None
    return manifest


def manifests_match(left: Optional[Dict[str, Any]], right: Dict[str, Any]) -> bool:
    if left is None:
        return False
    keys = ('schema_version', 'repository', 'release_id', 'tag_name', 'assets')
    return all(left.get(key) == right.get(key) for key in keys)


def write_manifest_atomic(filepath: pathlib.Path, manifest: Dict[str, Any]):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = filepath.with_name('{}.{}.tmp'.format(filepath.name, uuid.uuid4().hex))
    try:
        with temporary_path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary_path), str(filepath))
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _sha256_digest(digest: Optional[str]) -> Optional[str]:
    if not digest:
        return None

    try:
        algorithm, value = digest.split(':', 1)
    except ValueError:
        logging.warning('Unsupported asset digest format {}. Falling back to file size.'.format(digest))
        return None

    if algorithm.lower() != 'sha256' or len(value) != 64:
        logging.warning('Unsupported asset digest {}. Falling back to file size.'.format(digest))
        return None
    try:
        int(value, 16)
    except ValueError:
        logging.warning('Invalid SHA-256 asset digest {}. Falling back to file size.'.format(digest))
        return None
    return value.lower()


def _file_sha256(filepath: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with filepath.open('rb') as stream:
        while True:
            chunk = stream.read(hash_chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _file_size_matches(filepath: pathlib.Path, expected_size: Optional[int]) -> bool:
    if not filepath.is_file():
        return False
    return expected_size is None or filepath.stat().st_size == expected_size


def _file_matches_for_bootstrap(filepath: pathlib.Path, asset: Any) -> bool:
    if not _file_size_matches(filepath, asset.size):
        return False
    expected_sha256 = _sha256_digest(asset.digest)
    if expected_sha256 is None:
        return True
    return _file_sha256(filepath) == expected_sha256


def _validate_download(filepath: pathlib.Path, asset: Any):
    if not _file_size_matches(filepath, asset.size):
        actual_size = filepath.stat().st_size if filepath.exists() else None
        raise Exception('File length mismatch for {}. Got {}, expected {}.'.format(
            asset.name, actual_size, asset.size))

    expected_sha256 = _sha256_digest(asset.digest)
    if expected_sha256 is not None:
        actual_sha256 = _file_sha256(filepath)
        if actual_sha256 != expected_sha256:
            raise Exception('SHA-256 mismatch for {}. Got {}, expected {}.'.format(
                asset.name, actual_sha256, expected_sha256))


def _safe_asset_path(directory: pathlib.Path, asset_name: str) -> pathlib.Path:
    if not asset_name or pathlib.PurePath(asset_name).name != asset_name:
        raise Exception('Unsafe release asset name {}'.format(asset_name))
    return directory / asset_name


def sync_release_assets(
    artifacts: Any,
    destination_dir: pathlib.Path,
    part_dir: pathlib.Path,
    manifest: Optional[Dict[str, Any]],
    download: Callable[..., None],
    headers: Optional[Dict[str, str]] = None,
) -> SyncStats:
    destination_dir.mkdir(parents=True, exist_ok=True)
    part_dir.mkdir(parents=True, exist_ok=True)

    manifest_assets = manifest.get('assets', []) if manifest is not None else []
    manifest_by_id = {asset.get('id'): asset for asset in manifest_assets}
    manifest_by_name = {asset.get('name'): asset for asset in manifest_assets}
    remote_names = {asset.name for asset in artifacts.artifacts}
    stats = SyncStats()

    for asset in artifacts.artifacts:
        expected_manifest_asset = manifest_asset(asset)
        previous_by_id = manifest_by_id.get(asset.id)
        previous_by_name = manifest_by_name.get(asset.name)
        destination_path = _safe_asset_path(destination_dir, asset.name)

        metadata_unchanged = previous_by_id == expected_manifest_asset
        if metadata_unchanged and _file_size_matches(destination_path, asset.size):
            stats.unchanged += 1
            continue

        known_asset = previous_by_id is not None or previous_by_name is not None
        can_bootstrap = not known_asset or _sha256_digest(asset.digest) is not None
        if can_bootstrap and _file_matches_for_bootstrap(destination_path, asset):
            stats.unchanged += 1
            continue

        action_is_modified = known_asset or destination_path.exists()
        temporary_path = part_dir / '{}.{}.part'.format(asset.id, uuid.uuid4().hex)
        try:
            download(asset.url, str(temporary_path), asset.size, headers=headers)
            _validate_download(temporary_path, asset)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(temporary_path), str(destination_path))
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        if action_is_modified:
            stats.modified += 1
        else:
            stats.added += 1

    for child in destination_dir.iterdir():
        if child.is_file() and child.name != 'readme.txt' and child.name not in remote_names:
            stats.preserved += 1

    return stats
