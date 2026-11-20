from redline_kit.core.textmap import normalize_needle
from redline_kit.parsers.docx_miner import mine_docx_document
from redline_kit.writers.docx_track import apply_docx_edits
from tests.conftest import EXACT_EDITS


def _key(clause_ref, find, replace, comment):
    return (clause_ref, normalize_needle(find or ""), replace, comment)


def test_docx_round_trip(contract):
    apply_docx_edits(contract, EXACT_EDITS)
    mined = mine_docx_document(contract)
    assert all(item.source == "track_changes" for item in mined)

    mined_keys = sorted(
        _key(item.clause_ref, item.find, item.replace, item.comment) for item in mined
    )
    clause_by_find = {(item.find, item.replace): item.clause_ref for item in mined}
    expected_keys = sorted(
        _key(
            edit.clause_ref or clause_by_find[(edit.find, edit.replace)],
            edit.find,
            edit.replace,
            edit.comment,
        )
        for edit in EXACT_EDITS
    )
    assert mined_keys == expected_keys


def test_example_edits_round_trip(contract, example_edits):
    result = apply_docx_edits(contract, example_edits)
    mined = mine_docx_document(contract)
    changes = [item for item in mined if item.source == "track_changes"]
    comments = [item for item in mined if item.source == "comment"]
    assert len(changes) == len(result.applied)
    assert len(comments) == len(result.unmatched) == 1
    fuzzy = next(outcome for outcome in result.outcomes if outcome.method == "fuzzy")
    assert any(item.find == fuzzy.matched_text for item in changes)
