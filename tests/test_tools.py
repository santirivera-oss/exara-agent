"""Smoke tests for file/search/git tools."""
from __future__ import annotations

import pytest

from ai_agent.tools.base import ToolContext
from ai_agent.tools.file_ops import (
    CreateFile, DeleteFile, EditFile, ListDirectory, MultiEdit, ReadFile, WriteFile,
)
from ai_agent.tools.search import SearchProject


class _Dummy:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(workspace=tmp_path, settings=None, logger=_Dummy())


async def test_create_then_read(ctx):
    create = CreateFile()
    r = await create.run({"path": "hello.txt", "content": "hi\nthere"}, ctx)
    assert r.success, r.error

    read = ReadFile()
    r = await read.run({"path": "hello.txt"}, ctx)
    assert r.success
    assert "hi" in r.output
    assert "there" in r.output


async def test_create_existing_fails(ctx):
    create = CreateFile()
    await create.run({"path": "a.txt", "content": "x"}, ctx)
    r = await create.run({"path": "a.txt", "content": "y"}, ctx)
    assert not r.success


async def test_edit_file(ctx):
    await WriteFile().run({"path": "f.py", "content": "def x():\n    return 1\n"}, ctx)
    r = await EditFile().run(
        {"path": "f.py", "old_string": "return 1", "new_string": "return 42"}, ctx
    )
    assert r.success
    read = await ReadFile().run({"path": "f.py"}, ctx)
    assert "return 42" in read.output


async def test_edit_missing_old_string(ctx):
    await WriteFile().run({"path": "f.txt", "content": "abc"}, ctx)
    r = await EditFile().run({"path": "f.txt", "old_string": "ZZZ", "new_string": "."}, ctx)
    assert not r.success


async def test_edit_ambiguous_match(ctx):
    await WriteFile().run({"path": "f.txt", "content": "x x x"}, ctx)
    r = await EditFile().run({"path": "f.txt", "old_string": "x", "new_string": "y"}, ctx)
    assert not r.success
    r = await EditFile().run(
        {"path": "f.txt", "old_string": "x", "new_string": "y", "replace_all": True}, ctx
    )
    assert r.success


async def test_list_directory(ctx):
    await CreateFile().run({"path": "a/b.txt", "content": "z"}, ctx)
    r = await ListDirectory().run({"path": ".", "recursive": True}, ctx)
    assert r.success
    assert "b.txt" in r.output


async def test_list_directory_skips_cache_dirs_by_default(ctx, tmp_path):
    # Create real files inside ignored dirs to make sure they get filtered.
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("bytecode")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lodash.js").write_text("//")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")

    r = await ListDirectory().run({"path": ".", "recursive": True}, ctx)
    assert r.success
    assert "src" in r.output and "main.py" in r.output
    assert "__pycache__" not in r.output
    assert "lodash" not in r.output

    # include_cache=True should bring them back
    r2 = await ListDirectory().run({"path": ".", "recursive": True, "include_cache": True}, ctx)
    assert "__pycache__" in r2.output
    assert "lodash" in r2.output


async def test_delete_file(ctx):
    await CreateFile().run({"path": "t.txt", "content": "x"}, ctx)
    r = await DeleteFile().run({"path": "t.txt"}, ctx)
    assert r.success
    r = await ReadFile().run({"path": "t.txt"}, ctx)
    assert not r.success


async def test_search_project(ctx):
    await CreateFile().run({"path": "a.py", "content": "def foo(): pass\n"}, ctx)
    await CreateFile().run({"path": "b.py", "content": "def bar(): pass\n"}, ctx)
    r = await SearchProject().run({"pattern": r"def \w+", "mode": "content"}, ctx)
    assert r.success
    assert "foo" in r.output and "bar" in r.output


async def test_path_escape_blocked(ctx):
    r = await ReadFile().run({"path": "../../../etc/passwd"}, ctx)
    assert not r.success
    assert "outside workspace" in (r.error or "").lower()


async def test_multi_edit_applies_in_order(ctx):
    await WriteFile().run({"path": "src.py", "content": "def foo():\n    return 1\n\ndef bar():\n    return 2\n"}, ctx)
    r = await MultiEdit().run({
        "path": "src.py",
        "edits": [
            {"old_string": "return 1", "new_string": "return 10"},
            {"old_string": "return 2", "new_string": "return 20"},
        ],
    }, ctx)
    assert r.success, r.error
    content = (await ReadFile().run({"path": "src.py"}, ctx)).output
    assert "return 10" in content and "return 20" in content


async def test_multi_edit_atomic_on_failure(ctx):
    await WriteFile().run({"path": "x.txt", "content": "alpha beta gamma"}, ctx)
    # Second edit will fail (missing). First edit must NOT persist.
    r = await MultiEdit().run({
        "path": "x.txt",
        "edits": [
            {"old_string": "alpha", "new_string": "AAAA"},
            {"old_string": "MISSING", "new_string": "x"},
        ],
    }, ctx)
    assert not r.success
    content = (await ReadFile().run({"path": "x.txt"}, ctx)).output
    assert "alpha" in content and "AAAA" not in content


async def test_read_file_rejects_binary(ctx, tmp_path):
    bin_path = tmp_path / "blob.bin"
    bin_path.write_bytes(b"SQLite format 3\x00\x00\x00\x10" + bytes(range(256)) * 4)
    r = await ReadFile().run({"path": "blob.bin"}, ctx)
    assert not r.success
    assert "binary" in (r.error or "").lower()
