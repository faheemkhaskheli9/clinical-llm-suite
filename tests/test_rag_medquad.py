import zipfile

import pytest

from clinical_core.rag.fetchers import medquad
from clinical_core.rag.fetchers.medquad import EXCLUDED_DIR_NAMES, _ensure_extracted, _parse_file

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document id="0000123" source="CancerGov" url="https://www.cancer.gov/example">
  <Focus>Example Cancer</Focus>
  <QAPairs>
    <QAPair pid="1">
      <Question qid="0000123-1" qtype="symptoms">What are the symptoms of example cancer?</Question>
      <Answer>Symptoms include fatigue and unexplained weight loss.</Answer>
    </QAPair>
    <QAPair pid="2">
      <Question qid="0000123-2" qtype="treatment">How is example cancer treated?</Question>
      <Answer></Answer>
    </QAPair>
  </QAPairs>
</Document>"""


def test_parse_file_yields_one_document_per_complete_qa_pair(tmp_path):
    path = tmp_path / "0000123_1.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    docs = list(_parse_file(path))

    assert len(docs) == 1  # the empty-answer pair is skipped
    doc = docs[0]
    assert doc.id == "medquad:0000123:1"
    assert doc.doc_type == "qa"
    assert doc.source == "medquad"
    assert doc.url == "https://www.cancer.gov/example"
    assert doc.metadata == {"focus": "Example Cancer", "original_source": "CancerGov"}
    assert "Q: What are the symptoms" in doc.text
    assert "A: Symptoms include fatigue" in doc.text


def test_parse_file_returns_nothing_for_malformed_xml(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<Document><QAPairs>not closed", encoding="utf-8")

    assert list(_parse_file(path)) == []


def _patch_paths(monkeypatch, tmp_path):
    extract_root = tmp_path / "medquad"
    extracted_dir = extract_root / "MedQuAD-master"
    monkeypatch.setattr(medquad, "EXTRACT_ROOT", extract_root)
    monkeypatch.setattr(medquad, "EXTRACTED_DIR", extracted_dir)

    def fake_raw_cache_path(source, name):
        path = tmp_path / "raw" / source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(medquad, "raw_cache_path", fake_raw_cache_path)
    return extract_root, extracted_dir


def _fake_archive(zip_path, *, entries):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, body in entries.items():
            zf.writestr(name, body)


def test_ensure_extracted_atomically_publishes_a_complete_tree(monkeypatch, tmp_path):
    _extract_root, extracted_dir = _patch_paths(monkeypatch, tmp_path)

    def fake_get_bytes(session, url, *, cache_path):
        _fake_archive(cache_path, entries={"MedQuAD-master/1_CancerGov_QA/a.xml": "<Document/>"})
        return b""

    monkeypatch.setattr(medquad, "get_bytes", fake_get_bytes)

    result = _ensure_extracted(session=None)

    assert result == extracted_dir
    assert (extracted_dir / "1_CancerGov_QA" / "a.xml").is_file()
    assert not (extracted_dir.parent / ".extract-tmp").exists()


def test_ensure_extracted_discards_corrupt_zip_so_next_run_redownloads(monkeypatch, tmp_path):
    _extract_root, extracted_dir = _patch_paths(monkeypatch, tmp_path)
    calls = {"n": 0}

    def fake_get_bytes(session, url, *, cache_path):
        calls["n"] += 1
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"not a zip file")
        return b""

    monkeypatch.setattr(medquad, "get_bytes", fake_get_bytes)

    with pytest.raises(zipfile.BadZipFile):
        _ensure_extracted(session=None)

    assert not extracted_dir.exists()
    # The corrupt cache file was removed, not left to fail forever.
    assert not (tmp_path / "raw" / "medquad" / "medquad.zip").exists()


def test_excluded_dirs_are_the_three_copyright_stripped_mplus_subsets():
    # Regression guard: these are the only 3 of 12 MedQuAD source folders
    # whose <Answer> text is stripped (see the dataset's own readme.txt).
    # Silently including them yields well-formed but answer-less documents
    # that pass schema validation while being useless for RAG or eval.
    assert EXCLUDED_DIR_NAMES == {
        "10_MPlus_ADAM_QA",
        "11_MPlusDrugs_QA",
        "12_MPlusHerbsSupplements_QA",
    }
