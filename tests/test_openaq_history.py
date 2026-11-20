import json
import pandas as pd
from src.iot_openaq.history import pages
from src.iot_openaq import process


def test_pagination():
    class Response:
        def __init__(self, n): self.n = n
        def raise_for_status(self): pass
        def json(self): return {'results': list(range(self.n))}
    class Session:
        def get(self, url, params, timeout):
            return Response(1000 if params['page'] == 1 else 2)
    assert len(list(pages(Session(), '/locations', {}))) == 1002


def test_clean_keeps_old_data(tmp_path, monkeypatch):
    raw = tmp_path / 'raw';raw.mkdir()
    out = tmp_path / 'processed'
    monkeypatch.setattr(process, 'RAW_DIR', raw)
    monkeypatch.setattr(process, 'PROCESSED_DIR', out)
    rows = [dict(city='Paris',sensor_id=1,pollutant='no2',unit='µg/m³',value=20,timestamp='2021-01-01T00:00:00Z')]
    (raw / 'history_test.json').write_text(json.dumps(rows))
    process.process_openaq()
    assert len(pd.read_parquet(out / 'pollution_clean.parquet')) == 1
