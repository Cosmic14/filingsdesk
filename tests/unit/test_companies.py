from filingsdesk.rag.companies import match_symbols, strip_companies

INSTRUMENTS = [
    ("AAPL", "Apple Inc."),
    ("MSFT", "MICROSOFT CORP"),
    ("AMZN", "AMAZON COM INC"),
    ("GOOGL", "Alphabet Inc."),
    ("NVDA", "NVDA"),  # name never fetched: only the ticker matches
]
ALIASES = "GOOGL:google,AMZN:aws"


def test_registrant_names_and_tickers_match():
    assert match_symbols("What did Microsoft say about capex?", INSTRUMENTS, ALIASES) == ["MSFT"]
    assert match_symbols("How fast is NVDA growing?", INSTRUMENTS, ALIASES) == ["NVDA"]
    assert match_symbols("Compare Apple and Alphabet buybacks", INSTRUMENTS, ALIASES) == [
        "AAPL",
        "GOOGL",
    ]


def test_aliases_and_no_company():
    assert match_symbols("What risks does AWS face?", INSTRUMENTS, ALIASES) == ["AMZN"]
    assert match_symbols("Is Google investing in AI?", INSTRUMENTS, ALIASES) == ["GOOGL"]
    assert match_symbols("Which company grew fastest?", INSTRUMENTS, ALIASES) == []


def test_ticker_needs_exact_case_and_word():
    # "nvda" in lower case or inside another word is not a ticker mention
    assert match_symbols("the snvdas thing", INSTRUMENTS, ALIASES) == []


def test_strip_companies_leaves_the_useful_terms():
    stripped = strip_companies("How many employees does Microsoft have?", INSTRUMENTS, ALIASES)
    assert "Microsoft" not in stripped and "employees" in stripped
    assert "Apple" not in strip_companies("What were Apple's Services sales?", INSTRUMENTS, ALIASES)
