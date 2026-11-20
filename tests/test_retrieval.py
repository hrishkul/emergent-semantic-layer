import pandas as pd

from esl.corpus import passages_from_docs
from esl.db import connect
from esl.ontology import DOC_SHEETS
from esl.retrieval import HashEmbedder, Passage, bm25_ranking, replace_passages


def _docs() -> dict[str, pd.DataFrame]:
    frames = {sheet: pd.DataFrame([{"Table Name": "Unused"}]) for sheet in DOC_SHEETS}
    frames["Column Dictionary"] = pd.DataFrame(
        [
            {
                "Table": "Customers",
                "Column Name": "Customer_Name",
                "Data Type": "VARCHAR",
                "Description / Notes": "Official customer name",
            },
            {
                "Table": "Customers",
                "Column Name": "Customer_Name",
                "Data Type": "VARCHAR",
                "Description / Notes": "duplicate column row",
            },
            {"Table": "", "Column Name": "", "Data Type": "", "Description / Notes": ""},
        ]
    )
    frames["Relationships"] = pd.DataFrame(
        [
            {
                "Child Table": "Customers",
                "Child Column": "Company_ID",
                "Parent Table": "Companies",
                "Parent Key": "Company_ID",
                "Child Component": "Sales",
                "Parent Component": "Foundation",
                "Optional?": "Mandatory",
            }
        ]
    )
    frames["Table Index"] = pd.DataFrame(
        [
            {
                "Table Name": "Customers",
                "Component": "Sales",
                "Module": "Sales",
                "Primary Key": "Customer_ID",
                "Table Category": "Master",
            }
        ]
    )
    return frames


def test_bm25_ranks_the_document_that_uses_the_term() -> None:
    ranking = bm25_ranking(
        "cat",
        [("mat", "the cat sat on the mat"), ("log", "the dog sat on the log")],
    )
    assert ranking[0] == "mat"


def test_passages_skip_blanks_and_disambiguate_duplicates() -> None:
    passages = passages_from_docs(_docs(), corpus="fixture")
    column = [p for p in passages if p.sheet == "Column Dictionary"]
    assert [p.locator for p in column] == ["Customers.Customer_Name", "Customers.Customer_Name #2"]
    relationship = next(p for p in passages if p.sheet == "Relationships")
    assert relationship.locator == "Customers.Company_ID -> Companies.Company_ID"


def test_search_returns_the_cited_passage(client, database_url: str) -> None:
    passages = [
        Passage(
            "fixture",
            "Column Dictionary",
            "Customers.Customer_Name",
            "Column Dictionary Customers Customer_Name Official customer company name",
        ),
        Passage(
            "fixture",
            "Complexity Rules",
            "Deep complex",
            "Complexity Rules Deep complex dependency tables weight",
        ),
    ]
    embedder = HashEmbedder()
    with connect(database_url) as conn:
        replace_passages(conn, passages, embedder.embed([p.body for p in passages]))
        conn.commit()
    response = client.get(
        "/search",
        params={"q": "official customer company name", "corpus": "fixture"},
    )
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits[0]["sheet"] == "Column Dictionary"
    assert hits[0]["locator"] == "Customers.Customer_Name"
    assert "Official customer company name" in hits[0]["text"]
