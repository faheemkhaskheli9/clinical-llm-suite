from clinical_core.rag.fetchers.medlineplus import _clean, _is_valid_wsearch_xml, _parse_response

SAMPLE_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<nlmSearchResult>
  <term>diabetes</term>
  <count>1</count>
  <list num="1" start="0" per="1">
    <document rank="1" url="https://medlineplus.gov/diabetes.html">
      <content name="title">&lt;span class="qt0"&gt;Diabetes&lt;/span&gt;</content>
      <content name="organizationName">National Library of Medicine</content>
      <content name="altTitle">&lt;span class="qt0"&gt;Diabetes Mellitus&lt;/span&gt;</content>
      <content name="FullSummary">What is &lt;span class="qt0"&gt;diabetes&lt;/span&gt;?&lt;p&gt;A disease in which blood glucose is too high.&lt;/p&gt;</content>
    </document>
  </list>
</nlmSearchResult>"""

EMPTY_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<nlmSearchResult>
  <term>zzz-no-match</term>
  <count>0</count>
  <list num="0" start="0" per="0"></list>
</nlmSearchResult>"""


def test_clean_strips_highlight_spans_and_decodes_entities():
    assert _clean('<span class="qt0">Diabetes</span> &amp; you') == "Diabetes & you"


def test_clean_preserves_clinical_threshold_notation():
    # '<' as a comparison operator must NOT be mistaken for an HTML tag open.
    assert _clean("keep eGFR &lt;60 mL/min and BP &lt;120/80 mmHg") == "keep eGFR <60 mL/min and BP <120/80 mmHg"
    assert _clean("platelets &gt;50 x10^9/L") == "platelets >50 x10^9/L"


def test_is_valid_wsearch_xml_rejects_html_error_page_and_garbage():
    assert _is_valid_wsearch_xml(SAMPLE_RESPONSE) is True
    assert _is_valid_wsearch_xml("<html><body>Service unavailable</body></html>") is False
    assert _is_valid_wsearch_xml("<nlmSearchResult><list>trunc") is False


def test_parse_response_returns_nothing_for_malformed_xml():
    assert list(_parse_response("<nlmSearchResult><list>not closed", "diabetes")) == []


def test_parse_response_yields_one_document_with_clean_text():
    docs = list(_parse_response(SAMPLE_RESPONSE, "diabetes"))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "medlineplus:diabetes"
    assert doc.title == "Diabetes"
    assert doc.source == "medlineplus"
    assert doc.doc_type == "disease"
    assert doc.url == "https://medlineplus.gov/diabetes.html"
    assert "<span" not in doc.text
    assert "blood glucose is too high" in doc.text
    assert doc.metadata == {"query_term": "diabetes"}


def test_parse_response_yields_nothing_for_zero_results():
    assert list(_parse_response(EMPTY_RESPONSE, "zzz-no-match")) == []
