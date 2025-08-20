from app.validation import validate_config_payload

def test_ok():
    doc = {"version": 1, "database": {"host": "db", "port": 5432}}
    assert validate_config_payload(doc) == []

def test_missing():
    doc = {"database": {"port": 5432}}
    errs = validate_config_payload(doc)
    assert "Missing required field: database.host" in errs
