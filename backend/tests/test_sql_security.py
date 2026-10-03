import pytest
from app.services.analysis_tools import validate_readonly_query


@pytest.mark.parametrize('query', [
    'SELECT * FROM dataset_1 a JOIN dataset_1 b ON a.sales=b.sales',
    'SELECT sales FROM dataset_1 WHERE sales IN (SELECT sales FROM dataset_1)',
    'WITH x AS (SELECT sales FROM dataset_1) SELECT sales FROM x',
    'SELECT UUID() FROM dataset_1',
    'SELECT @x FROM dataset_1',
    'SELECT /* hint */ sales FROM dataset_1',
])
def test_sql_rejects_complex_or_unapproved_features(query):
    with pytest.raises(ValueError):
        validate_readonly_query(query, 1, {'sales'}, 10)


def test_select_star_expands_authorized_columns():
    result = validate_readonly_query('SELECT * FROM dataset_1', 1, {'sales', 'region'}, 10)
    assert '*' not in result
    assert 'sales' in result and 'region' in result
