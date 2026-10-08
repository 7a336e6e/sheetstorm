"""Remote transport: per-user artifact directories, traversal and symlink rejection."""

from __future__ import annotations

import os
import stat

import pytest

from sheetstorm_mcp import server
from sheetstorm_mcp.client import Grant
from sheetstorm_mcp.tools import artifacts

I = "inc-1"  # noqa: E741


@pytest.fixture
def as_user(monkeypatch, make_client, backend, tmp_path):
    root = tmp_path / "artifacts"
    make_client("sse", ARTIFACT_DIR=str(root))
    current = {}
    monkeypatch.setattr(artifacts, "current_grant", lambda: current.get("g"))
    monkeypatch.setattr(server, "current_grant", lambda: current.get("g"))

    def _switch(user_id, org="org-1"):
        current["g"] = Grant(grant_id=f"g-{user_id}", client_id="c", scopes=[],
                             sheetstorm_access_token=f"jwt-{user_id}", user_id=user_id, organization_id=org)
        return root / org / user_id

    return _switch


async def test_download_lands_in_private_per_user_dir(as_user, backend):
    alice_dir = as_user("alice")
    backend.set("GET", f"/incidents/{I}/artifacts/a1/download", b"MZ-alice")
    out = await artifacts.sheetstorm_download_artifact(I, "a1", save_path="case/mal.bin")
    assert out.startswith("✓"), out
    target = alice_dir / "case" / "mal.bin"
    assert target.read_bytes() == b"MZ-alice"
    assert stat.S_IMODE(os.stat(alice_dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(alice_dir.parent).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert backend.find("GET", f"/incidents/{I}/artifacts/a1/download")["auth"] == "Bearer jwt-alice"


async def test_users_cannot_read_or_overwrite_each_other(as_user, backend):
    alice_dir = as_user("alice")
    alice_dir.mkdir(parents=True)
    (alice_dir / "secret.raw").write_bytes(b"alice-evidence")

    as_user("bob")
    # same relative path resolves inside bob's own sandbox
    out = await artifacts.sheetstorm_upload_artifact(I, "secret.raw")
    assert "File not found" in out
    for evil in ("../alice/secret.raw", "../../org-1/alice/secret.raw", str(alice_dir / "secret.raw"),
                 "/etc/passwd", "a/../../alice/secret.raw"):
        out = await artifacts.sheetstorm_upload_artifact(I, evil)
        assert out.startswith("✗"), (evil, out)
    backend.set("GET", f"/incidents/{I}/artifacts/a1/download", b"bob-overwrite")
    out = await artifacts.sheetstorm_download_artifact(I, "a1", save_path="../alice/secret.raw")
    assert out.startswith("✗")
    assert (alice_dir / "secret.raw").read_bytes() == b"alice-evidence"
    assert backend.find("POST", f"/incidents/{I}/artifacts") is None


async def test_symlinks_are_rejected(as_user, backend, tmp_path):
    bob_dir = as_user("bob")
    bob_dir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("host secret")
    os.symlink(outside, bob_dir / "link.txt")
    os.symlink(tmp_path, bob_dir / "linkdir")

    assert "Symlinks are not allowed" in await artifacts.sheetstorm_upload_artifact(I, "link.txt")
    assert "Symlinks are not allowed" in await artifacts.sheetstorm_upload_artifact(I, "linkdir/outside.txt")
    backend.set("GET", f"/incidents/{I}/artifacts/a1/download", b"x")
    out = await artifacts.sheetstorm_download_artifact(I, "a1", save_path="link.txt")
    assert "Symlinks are not allowed" in out
    assert outside.read_text() == "host secret"


async def test_upload_from_own_sandbox(as_user, backend):
    bob_dir = as_user("bob")
    (bob_dir / "case").mkdir(parents=True)
    (bob_dir / "case" / "mem.raw").write_bytes(b"RAM")
    backend.set("POST", f"/incidents/{I}/artifacts", {"id": "a9", "original_filename": "mem.raw"})
    out = await artifacts.sheetstorm_upload_artifact(I, "case/mem.raw")
    assert out.startswith("✓ Artifact uploaded")


async def test_path_tools_require_a_user_identity(monkeypatch, make_client, backend, tmp_path):
    make_client("sse", ARTIFACT_DIR=str(tmp_path))
    monkeypatch.setattr(artifacts, "current_grant", lambda: None)
    out = await artifacts.sheetstorm_upload_artifact(I, "x.bin")
    assert out.startswith("✗") and "user" in out


async def test_operator_root_dir_mode_is_not_changed(as_user, backend, tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    as_user("carol")
    await artifacts.sheetstorm_download_artifact(I, "a1", save_path="f.bin")
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o755
