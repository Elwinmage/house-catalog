"""Copy of the rules into the tools editing the catalog."""

from __future__ import annotations

from pathlib import Path

import sync_client


def test_sync(tmp_path: Path, capsys):
    assert sync_client.sync(tmp_path) == []
    assert "skip catalog-editor" in capsys.readouterr().out

    component = tmp_path / "catalog-editor/custom_components/catalog_editor"
    component.mkdir(parents=True)
    stale = ["catalog-editor/house_catalog_rules.py"]
    assert sync_client.sync(tmp_path, check=True) == stale
    assert list(component.iterdir()) == []

    assert sync_client.sync(tmp_path) == stale
    copy = (component / "house_catalog_rules.py").read_text(encoding="utf-8")
    source = (sync_client.REPO / "client/house_catalog_rules.py").read_text(
        encoding="utf-8"
    )
    assert copy == sync_client.HEADER.format(name="house_catalog_rules.py") + source
    assert copy.startswith("# Generated from house-catalog/client/")
    assert sync_client.sync(tmp_path, check=True) == []

    (component / "house_catalog_rules.py").write_text("edited", encoding="utf-8")
    assert sync_client.sync(tmp_path, check=True) == stale


def test_command(tmp_path: Path, capsys):
    (tmp_path / "catalog-editor/custom_components/catalog_editor").mkdir(parents=True)
    args = ["--base", str(tmp_path)]
    assert sync_client.main([*args, "--check"]) == 1
    assert (
        "out of date: catalog-editor/house_catalog_rules.py" in capsys.readouterr().out
    )
    assert sync_client.main(args) == 0
    assert "updated: catalog-editor/house_catalog_rules.py" in capsys.readouterr().out
    assert sync_client.main([*args, "--check"]) == 0
    assert "everything up to date" in capsys.readouterr().out
