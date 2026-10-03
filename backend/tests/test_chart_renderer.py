import io

import pytest
from PIL import Image

from app.charts.renderer import ChartRenderSpec, ChartRenderer, chart_spec_from_legacy


SIMPLE_SERIES = [{"name": "销售额", "data": [{"x": "华南", "y": 20}, {"x": "华东", "y": 35}]}]


@pytest.mark.parametrize("chart_type", [
    "bar", "line", "scatter", "histogram", "boxplot", "pie", "donut", "area", "waterfall", "funnel",
])
def test_supported_charts_render_svg_and_300dpi_3000x1800_png(chart_type):
    series = [{"name": "系列", "data": [{"x": "A", "y": 8}, {"x": "B", "y": 3}]}]
    if chart_type == "scatter":
        series = [{"name": "系列", "data": [{"x": 1, "y": 8}, {"x": 2, "y": 3}]}]
    if chart_type == "boxplot":
        series = [{"name": "销售额", "data": [{"x": "销售额", "values": [1, 3, 5, 8, 10]}]}]
    rendered = ChartRenderer().render({"chart_type": chart_type, "title": "华南销售额趋势", "series": series})
    image = Image.open(io.BytesIO(rendered.png))

    assert rendered.svg.lstrip().startswith(b"<?xml")
    assert image.size == (3000, 1800)
    assert image.info["dpi"][0] == pytest.approx(300, abs=0.5)
    assert Image.open(io.BytesIO(rendered.thumbnail_png)).size[0] <= 600


def test_heatmap_and_box_alias_are_rendered_and_legacy_spec_is_adapted():
    heatmap = ChartRenderer().render({"chart_type": "heatmap", "series": [
        {"name": "销售额", "values": [1, 2]}, {"name": "成本", "values": [3, 4]}]})
    legacy = chart_spec_from_legacy({"type": "bar", "title": "区域销售额",
        "dimension": {"field": "region", "label": "地区"},
        "metrics": [{"field": "sales", "label": "销售额"}],
        "series": [{"name": "销售额", "data": [{"name": "华南", "value": 20}]}]})
    rendered = ChartRenderer().render(legacy)

    assert heatmap.png.startswith(b"\x89PNG")
    assert legacy["x"] == "地区"
    assert legacy["series"][0]["data"][0] == {"x": "华南", "y": 20}
    assert rendered.png.startswith(b"\x89PNG")
    result_v2 = chart_spec_from_legacy({"chart_type": "bar", "title": "销售额", "x": "region", "y": ["sales"],
        "series": [{"name": "sales", "points": [{"x": "South", "y": 20}]}], "options": {"show_legend": False}})
    assert result_v2["series"][0]["data"] == [{"x": "South", "y": 20}]
    assert ChartRenderer().render({"chart_type": "box", "series": [
        {"name": "a", "data": [{"x": "a", "values": [1, 2, 3]}]}]}).png.startswith(b"\x89PNG")


def test_chart_renderer_rejects_non_finite_or_oversized_points():
    with pytest.raises(ValueError):
        ChartRenderer().render({"chart_type": "bar", "series": [{"name": "x", "data": [{"x": "a", "y": float("nan")}]}]})
    with pytest.raises(ValueError):
        ChartRenderSpec.model_validate({"chart_type": "bar", "series": [{"name": "x", "data": [{"x": index, "y": index} for index in range(501)]}]})
