import asyncio
import uuid

from memtype.jev import FakeJev

from engrim_trax.classify import TITLE_MAX, Classifier
from engrim_trax.edges import citation_edges, drop_newer, evidence_edges, supersession_edges
from engrim_trax.importer import IdMap, Importer, record_key, submit_body
from engrim_trax.records import cited_ids, load_records, load_vectors, metric_pairs, pr_numbers
from engrim_trax.sessions import import_sessions, list_sessions
from engrim_trax.tests.conftest import FakeClient, rule


def _classified(engrim_copy, tmp_path):
    records = load_records(engrim_copy)
    clf = Classifier(FakeJev(rule), tmp_path / "answers.jsonl")
    mappings = asyncio.run(clf.classify(records))
    return records, clf, mappings


def test_regex_prefill():
    assert cited_ids("Correction to #1 and PR #17325, see #42") == [1, 42]
    assert pr_numbers("PR #17325 and https://github.com/x/y/pull/99") == ["17325", "99"]
    assert metric_pairs("precision=0.91 recall=0.84 on 2026-09-05: 3 frames") == [("precision", 0.91), ("recall", 0.84)]


def test_kinds_bands_and_fields(engrim_copy, tmp_path):
    records, clf, m = _classified(engrim_copy, tmp_path)
    assert {r.type for r in records} == {"fact", "feedback", "state", "reference", "decision"}
    assert m[4].kind == "Issue" and m[4].status == "active" and m[4].fields == {"issue_kind": ["task"], "priority": 10}
    assert m[5].kind == "Issue" and m[5].status == "complete"
    assert m[2].kind == "Belief" and m[2].fields["judgement"] == "proven" and m[2].fields["confidence"] == 0.9
    assert m[1].fields["confidence"] == 0.2 and "engrim:superseded" in m[1].labels
    assert m[3].band == "review" and "jev:low-confidence" in m[3].labels and "feedback" in m[3].labels
    assert m[9].band == "fallback" and m[9].kind == "Belief" and "jev:fallback" in m[9].labels
    assert m[6].kind == "Experiment" and m[6].status == "complete"
    assert "precision" in m[6].fields["outcome"] and "threshold" in m[6].fields["config"]["setup"]
    assert m[6].metrics == [("precision", 0.91), ("recall", 0.84)]
    assert m[7].kind == "WebResult" and m[7].fields["url"] == "https://github.com/rekursiv-ai/trackinizer"
    assert m[8].kind == "Paper" and m[8].fields["source"] == "arXiv:2405.16391"
    assert len(m[9].title) <= TITLE_MAX and m[9].title.startswith("Decided")
    assert {"engrim", "engrim:state", "project:vlm-chat", "pr"} <= set(m[4].labels)
    assert "engrim id: 4 | type: state" in m[4].description and "ts: 2026-09-04" in m[4].description


def test_answer_cache_skips_jev(engrim_copy, tmp_path):
    records = load_records(engrim_copy)
    jev = FakeJev(rule)
    asyncio.run(Classifier(jev, tmp_path / "a.jsonl").classify(records))
    first = jev.calls
    jev2 = FakeJev(rule)
    clf2 = Classifier(jev2, tmp_path / "a.jsonl")
    asyncio.run(clf2.classify(records))
    assert first > 0 and jev2.calls == 0 and clf2.cache_hits == first


def test_edges(engrim_copy, tmp_path):
    records, clf, m = _classified(engrim_copy, tmp_path)
    by_id = {r.id: r for r in records}
    cites = citation_edges(records)
    assert any(e.src == 2 and e.dst == 1 and e.kind == "produced_by" for e in cites)
    assert any(e.src == 5 and e.dst == 4 and "pr 17325" in e.note for e in cites)
    assert not any(e.dst == 17325 for e in cites)
    sup, pairs = asyncio.run(supersession_edges(clf, records))
    assert [(e.src, e.dst, e.kind) for e in sup] == [(2, 1, "supersedes")] and pairs >= 1
    ev, _ = asyncio.run(evidence_edges(clf, records, m, load_vectors(engrim_copy)))
    assert ev and all(e.kind == "proves" and e.valence == 0.5 and e.src == 6 for e in ev)
    assert all(by_id[e.dst].when < by_id[e.src].when for e in ev)
    kept, dropped = drop_newer(cites + sup + ev + [type(sup[0])(1, 2, "produced_by")], by_id)
    assert dropped == 1 and len(kept) == len(cites) + len(sup) + len(ev)


def test_importer_is_idempotent(engrim_copy, tmp_path):
    records, clf, m = _classified(engrim_copy, tmp_path)
    by_id = {r.id: r for r in records}
    edges, _ = drop_newer(citation_edges(records) + asyncio.run(supersession_edges(clf, records))[0], by_id)
    client = FakeClient()
    idmap = IdMap(tmp_path / "idmap.json")
    imp = Importer(client, idmap)
    imp.submit_records(records, m)
    imp.submit_metrics(m)
    imp.submit_edges(edges)
    assert imp.stats["submitted"] == len(records) and len(client.submits) == len(records)
    assert [k for k, _ in client.submits] == [m[r.id].kind for r in records]  # oldest first
    assert imp.stats["edges_created"] == len(edges) and len(client.metrics) == 1
    body = submit_body(m[4], "george")
    assert body["owner"] == "george" and body["idempotency_key"] == str(record_key(4)) and body["status"] == "active"
    # second run from the persisted id map: no submits, no edges, no metrics
    imp2 = Importer(client, IdMap(tmp_path / "idmap.json"))
    imp2.submit_records(records, m)
    imp2.submit_metrics(m)
    imp2.submit_edges(edges)
    assert imp2.stats["submitted"] == 0 and imp2.stats["edges_created"] == 0 and imp2.stats["edges_skipped"] == len(edges)
    assert len(client.submits) == len(records) and len(client.edges) == len(edges) and len(client.metrics) == 1
    # a lost id map still replays on the server's idempotency key
    imp3 = Importer(client, IdMap(None))
    imp3.submit_records(records, m)
    assert imp3.stats["submitted"] == len(records) and len(client.submits) == len(records)
    assert imp3.idmap.get(4) == idmap.get(4)


def test_sessions(engrim_copy, tmp_path):
    infos = list_sessions(engrim_copy)
    assert [i.rows for i in infos] == [3, 1] and infos[0].title.startswith("claude session a5c58653 in main: hello there")
    assert infos[0].cli_session_id == "a5c58653-6edd-431d-90b8-a684ad6a13d5"
    client = FakeClient()
    idmap = IdMap(tmp_path / "idmap.json")
    stats = import_sessions(engrim_copy, client, idmap)
    assert stats == {"sessions": 2, "sessions_skipped": 0, "records_written": 4, "records_skipped": 0}
    sid = uuid.UUID(idmap.data["sessions"][infos[0].key]["id"])
    body = client.sessions[sid]["body"]
    assert body.cli == "claude" and body.started.isoformat().startswith("2026-09-07T07:30:39")
    assert client.sessions[sid]["ended"].isoformat().startswith("2026-09-07T07:31:00")
    rec = client.records[(sid, 0)]
    assert rec.kind == "UserMessage" and rec.text == "hello there" and rec.payload["extra"]["engrim_log_id"] == 1
    assert {l for s, l in client.labels if s == sid} == {"engrim", "engrim:log", "project:main"}
    again = import_sessions(engrim_copy, client, IdMap(tmp_path / "idmap.json"))
    assert again["sessions_skipped"] == 2 and again["records_written"] == 0
