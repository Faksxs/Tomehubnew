from services import book_metadata_resolver_service as resolver


def test_resolve_book_metadata_prefers_openlibrary_bib_for_isbn(monkeypatch):
    isbn = "9789750721311"

    monkeypatch.setattr(
        resolver,
        "_fetch_openlibrary_by_bib",
        lambda isbn_set: [
            {
                "title": "Tembellik Hakkı",
                "author": "Paul Lafargue",
                "publisher": "Is Bankasi Kultur Yayinlari",
                "isbn": isbn,
                "allIsbns": [isbn],
                "translator": "",
                "tags": [],
                "summary": "",
                "publishedDate": "2020",
                "url": "https://openlibrary.org/books/OL1M",
                "coverUrl": "https://covers.openlibrary.org/b/id/1-M.jpg?default=false",
                "pageCount": 120,
                "sourceLanguageHint": "tr",
                "_provider": "open-library-bib",
            }
        ],
    )
    monkeypatch.setattr(
        resolver,
        "_fetch_openlibrary_search",
        lambda query, isbn_mode, isbn_set: [
            {
                "title": "Tembellik Hakki",
                "author": "Paul Lafargue",
                "publisher": "",
                "isbn": isbn,
                "allIsbns": [isbn],
                "translator": "",
                "tags": [],
                "summary": "",
                "publishedDate": "",
                "url": "",
                "coverUrl": None,
                "pageCount": None,
                "sourceLanguageHint": "",
                "_provider": "open-library",
            }
        ],
    )
    monkeypatch.setattr(
        resolver,
        "_fetch_google_books",
        lambda query, isbn_set: [
            {
                "title": "Lazy Right",
                "author": "Paul Lafargue",
                "publisher": "",
                "isbn": isbn,
                "allIsbns": [isbn],
                "translator": "",
                "tags": [],
                "summary": "",
                "publishedDate": "",
                "url": "",
                "coverUrl": None,
                "pageCount": None,
                "sourceLanguageHint": "en",
                "_provider": "google-books",
            }
        ],
    )
    monkeypatch.setattr(resolver, "_verify_cover_urls", lambda items, top_n=3: None)

    results = resolver.resolve_book_metadata(isbn, limit=10)
    assert len(results) == 1
    assert results[0]["_provider"] == "open-library-bib"
    assert results[0]["isbn"] == isbn


def test_resolve_book_metadata_text_query_merges_and_limits(monkeypatch):
    monkeypatch.setattr(resolver, "_fetch_openlibrary_by_bib", lambda isbn_set: [])
    monkeypatch.setattr(
        resolver,
        "_fetch_openlibrary_search",
        lambda query, isbn_mode, isbn_set: [
            {
                "title": "Hayatin Anlami",
                "author": "Terry Eagleton",
                "publisher": "Sel",
                "isbn": "",
                "allIsbns": [],
                "translator": "",
                "tags": [],
                "summary": "",
                "publishedDate": "2012",
                "url": "",
                "coverUrl": None,
                "pageCount": 200,
                "sourceLanguageHint": "tr",
                "_provider": "open-library",
            }
        ],
    )
    monkeypatch.setattr(
        resolver,
        "_fetch_google_books",
        lambda query, isbn_set: [
            {
                "title": "Hayatin Anlami",
                "author": "Terry Eagleton",
                "publisher": "Sel",
                "isbn": "",
                "allIsbns": [],
                "translator": "",
                "tags": [],
                "summary": "",
                "publishedDate": "2012",
                "url": "",
                "coverUrl": None,
                "pageCount": 200,
                "sourceLanguageHint": "tr",
                "_provider": "google-books",
            }
        ],
    )
    monkeypatch.setattr(resolver, "_verify_cover_urls", lambda items, top_n=3: None)

    results = resolver.resolve_book_metadata("Hayatın Anlamı Terry Eagleton", limit=5)
    assert len(results) == 1
    assert results[0]["title"] == "Hayatin Anlami"


def test_map_openlibrary_bib_transliterates_cyrillic_author_in_latin_context():
    cyr_author = "\u041c\u0430\u043a\u0441\u0438\u043c \u0413\u043e\u0440\u044c\u043a\u0438\u0439"
    entry = {
        "title": "Artamonovlar",
        "authors": [{"name": cyr_author}],
        "publishers": [{"name": "Is Bankasi Kultur Yayinlari"}],
        "identifiers": {"isbn_13": ["9786052951798"]},
        "cover": {"medium": "https://covers.openlibrary.org/b/id/42-M.jpg"},
    }
    mapped = resolver._map_openlibrary_bib_entry(entry, {"9786052951798"})
    assert mapped is not None
    assert mapped["author"] != cyr_author
    assert "Maksim" in mapped["author"]
