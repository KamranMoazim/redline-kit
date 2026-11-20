from docx.oxml import parse_xml
from lxml import etree

from redline_kit.core.matching import find_match
from redline_kit.core.textmap import build_text_map, normalize, split_run, w

W_DECL = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def test_normalize_keeps_offsets_back_to_original():
    original = "the “Agreement”  dated 1 Nov"
    normalized, index_map = normalize(original)
    assert normalized == 'the "Agreement" dated 1 Nov'
    assert original[index_map[normalized.index("dated")] :].startswith("dated")


def test_text_map_skips_deleted_runs_and_markup():
    paragraph = parse_xml(
        f"<w:p {W_DECL}><w:r><w:t>Hello </w:t></w:r><w:proofErr w:type='spellStart'/>"
        "<w:del w:id='1' w:author='a'><w:r><w:delText>old </w:delText></w:r></w:del>"
        "<w:hyperlink><w:r><w:t>world</w:t></w:r></w:hyperlink><w:r><w:tab/><w:t>!</w:t></w:r></w:p>"
    )
    assert build_text_map(paragraph).text == "Hello world\t!"


def test_split_run_copies_formatting():
    paragraph = parse_xml(
        f"<w:p {W_DECL}><w:r><w:rPr><w:b/></w:rPr><w:t>Contractor</w:t></w:r></w:p>"
    )
    run = paragraph.find(w("r"))
    right = split_run(run, 4)
    assert run.find(w("t")).text == "Cont"
    assert right.find(w("t")).text == "ractor"
    assert right.find(f"{w('rPr')}/{w('b')}") is not None
    assert etree.QName(right.getprevious()).localname == "r"


def test_exact_match_picks_occurrence_and_fuzzy_respects_threshold():
    haystacks = ["pay within thirty (30) days", "claims within thirty (30) days"]
    assert find_match(haystacks, "within thirty (30) days", occurrence=2).haystack_index == 1
    assert find_match(haystacks, "within thirty (30) days", occurrence=3) is None
    fuzzy = find_match(
        ["furnish all labor, materials and equipment"], "furnish all labour, materials"
    )
    assert fuzzy is not None and fuzzy.method == "fuzzy"
    assert find_match(["furnish all labor"], "something completely different") is None
