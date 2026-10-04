from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any, Literal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator


CHART_TYPES = {"bar", "line", "scatter", "histogram", "boxplot", "box", "heatmap",
               "pie", "donut", "area", "waterfall", "funnel"}
PALETTE = ["#2F6BFF", "#18A999", "#F1A84A", "#8368D8", "#E56D7B", "#3C9CCB", "#82B65D", "#D17BA8"]


class ChartRenderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    chart_type: Literal["bar", "line", "scatter", "histogram", "boxplot", "box", "heatmap",
                        "pie", "donut", "area", "waterfall", "funnel"]
    title: str = Field(default="数据分析图表", max_length=160)
    x: str | None = Field(default=None, max_length=128)
    y: list[str] = Field(default_factory=list, max_length=20)
    series: list[dict[str, Any]] = Field(min_length=1, max_length=80)
    show_legend: bool = True
    stacked: bool = False
    currency: str | None = Field(default=None, max_length=8)
    value_format: Literal["number", "percent", "currency"] = "number"

    @field_validator("series")
    @classmethod
    def bounded_series(cls, value):
        for series in value:
            points = series.get("data", series.get("values"))
            if not isinstance(points, list) or len(points) > 500:
                raise ValueError("Chart series exceed the 500 point budget")
        return value


@dataclass(frozen=True)
class ChartFiles:
    svg: bytes
    png: bytes
    thumbnail_png: bytes
    width: int = 3000
    height: int = 1800
    dpi: int = 300


def chart_spec_from_legacy(payload: dict[str, Any], *, chart_type: str | None = None) -> dict[str, Any]:
    """Adapt the v1 ChartSpec shape without fetching or recalculating its source data."""
    if payload.get("chart_type"):
        normalized = []
        for series in payload.get("series", []):
            points = series.get("points", series.get("data", []))
            if payload.get('chart_type') == 'heatmap' and 'values' in series:
                normalized.append({'name':series.get('name') or '系列','values':series['values']})
                continue
            data = [{"x": point.get("x", point.get("name")),
                     "y": point.get("y", point.get("value")),
                     **({k:point[k] for k in ('lower','upper') if k in point}),
                     **({"values": point["values"]} if point.get("values") else {})}
                    for point in points]
            normalized.append({"name": series.get("name") or "系列",
                **({"values": [point.get("values", [None])[0] for point in points]}
                   if payload.get("chart_type") == "heatmap" and points else {"data": data})})
        return {"chart_type": chart_type or payload["chart_type"],
                "title": payload.get("title") or "数据分析图表", "x": payload.get("x"),
                "y": payload.get("y") or [], "series": normalized,
                "show_legend": (payload.get("options") or {}).get("show_legend", True),
                "stacked": (payload.get("options") or {}).get("stacked", False)}
    dimension = payload.get("dimension") or {}
    metrics = payload.get("metrics") or []
    return {
        "chart_type": chart_type or payload.get("type") or "bar",
        "title": payload.get("title") or "数据分析图表",
        "x": dimension.get("label") or dimension.get("field"),
        "y": [item.get("label") or item.get("field") for item in metrics],
        "series": [{"name": item.get("name") or "系列", "data": [
            ({"x": point['value'][0], "y": point['value'][1]} if (chart_type or payload.get('type')) == 'scatter' and isinstance(point.get('value'), list) else
             {"x": point.get("name"), "values": point['value']} if (chart_type or payload.get('type')) in {'box','boxplot'} and isinstance(point.get('value'), list) else
             {"x": point.get("name"), "y": (point.get("value")[-1] if isinstance(point.get("value"), list) else point.get("value"))})
            for point in item.get("data", [])
        ]} for item in payload.get("series", [])],
        "show_legend": True,
    }


class ChartRenderer:
    def render(self, spec: ChartRenderSpec | dict[str, Any]) -> ChartFiles:
        spec = spec if isinstance(spec, ChartRenderSpec) else ChartRenderSpec.model_validate(spec)
        chart_type = "boxplot" if spec.chart_type == "box" else spec.chart_type
        plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": [
            "Noto Sans CJK SC", "Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "axes.unicode_minus": False, "svg.fonttype": "none"})
        figure, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
        figure.patch.set_facecolor("white")
        axis.set_facecolor("white")
        series = spec.series
        if chart_type in {"pie", "donut"}:
            labels = [str(item.get("x", "")) for item in series[0]["data"]]
            values = [self._number(item.get("y")) for item in series[0]["data"]]
            if any(value < 0 for value in values):
                raise ValueError("PIE_NEGATIVE_VALUE")
            axis.pie(values, labels=labels, autopct="%1.1f%%", colors=PALETTE, startangle=90,
                     wedgeprops={"width": 0.48} if chart_type == "donut" else None)
        elif chart_type == "heatmap":
            matrix = [item.get("values", []) for item in series]
            if not matrix or not matrix[0]:
                raise ValueError("CHART_DATA_EMPTY")
            image = axis.imshow(np.asarray(matrix, dtype=float), aspect="auto", cmap="Blues")
            axis.set_yticks(range(len(series)), [str(item.get("name", "")) for item in series])
            figure.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
        elif chart_type == "boxplot":
            values, labels = [], []
            for item in series:
                points = item.get("data") or []
                for point in points:
                    raw = point.get("values") if isinstance(point, dict) else None
                    if raw:
                        values.append([self._number(value) for value in raw])
                        labels.append(str(point.get("x", item.get("name", ""))))
                    elif point.get("y") is not None:
                        values.append([self._number(point["y"])])
                        labels.append(str(item.get("name", "")))
            if not values:
                raise ValueError("CHART_DATA_EMPTY")
            axis.boxplot(values, tick_labels=labels, patch_artist=True,
                         boxprops={"facecolor": "#DCE8FF", "edgecolor": PALETTE[0]},
                         medianprops={"color": PALETTE[1], "linewidth": 2})
        elif chart_type in {"waterfall", "funnel"}:
            points = series[0].get("data", [])
            labels = [str(point.get("x", "")) for point in points]
            values = [self._number(point.get("y")) for point in points]
            if chart_type == "waterfall":
                bottoms, cumulative = [], 0.0
                for value in values:
                    bottoms.append(cumulative if value >= 0 else cumulative + value)
                    cumulative += value
                axis.bar(labels, [abs(value) for value in values], bottom=bottoms,
                         color=[PALETTE[1] if value >= 0 else "#E56D7B" for value in values])
            else:
                axis.barh(labels[::-1], values[::-1], color=PALETTE[0])
        else:
            categories = list(dict.fromkeys(str(point.get("x", "")) for item in series for point in item.get("data", [])))
            positions = np.arange(len(categories))
            width = min(0.82 / max(1, len(series)), 0.36)
            for index, item in enumerate(series):
                points = item.get("data", [])
                point_map = {str(point.get("x", "")): point.get("y") for point in points}
                values = [self._number(point_map[label]) if point_map.get(label) is not None else np.nan for label in categories]
                color = PALETTE[index % len(PALETTE)]
                if chart_type == "line":
                    axis.plot(categories, values, marker="o", linewidth=2.3, label=item.get("name", ""), color=color)
                    bounds = {str(point.get('x','')):point for point in points}
                    if all(bounds.get(label,{}).get('lower') is not None and bounds.get(label,{}).get('upper') is not None for label in categories):
                        axis.fill_between(range(len(categories)),[self._number(bounds[label]['lower']) for label in categories],
                            [self._number(bounds[label]['upper']) for label in categories],color=color,alpha=.16,label='经验误差范围')
                elif chart_type == "scatter":
                    axis.scatter([self._number(point.get("x")) for point in points],
                                 [self._number(point.get("y")) for point in points], label=item.get("name", ""), color=color)
                elif chart_type == "area":
                    axis.fill_between(positions, values, alpha=0.22, color=color)
                    axis.plot(positions, values, label=item.get("name", ""), color=color)
                else:
                    offsets = np.zeros_like(positions, dtype=float) if not spec.stacked else np.zeros_like(positions, dtype=float)
                    if spec.stacked:
                        previous = np.zeros_like(positions, dtype=float)
                        for earlier in series[:index]:
                            earlier_map = {str(point.get("x", "")): point.get("y") for point in earlier.get("data", [])}
                            previous += np.asarray([self._number(earlier_map[label]) if earlier_map.get(label) is not None else 0 for label in categories])
                        offsets = previous
                    axis.bar(positions + (index - (len(series) - 1) / 2) * width,
                             values, width=width, bottom=offsets if spec.stacked else None,
                             label=item.get("name", ""), color=color)
            if chart_type not in {"scatter"}:
                axis.set_xticks(positions if chart_type in {"bar", "area", "histogram"} else range(len(categories)), categories, rotation=25, ha="right")
        axis.set_title(spec.title, loc="left", fontsize=15, pad=18, color="#17263D")
        if spec.x and chart_type not in {"pie", "donut", "heatmap", "funnel"}:
            axis.set_xlabel(spec.x, labelpad=10)
        if spec.value_format == "percent" and chart_type not in {"pie", "donut"}:
            axis.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        elif spec.value_format == "currency":
            symbol = spec.currency or "¥"
            axis.yaxis.set_major_formatter(lambda value, _: f"{symbol}{value:,.0f}")
        else:
            axis.yaxis.set_major_formatter(lambda value, _: f"{value:,.2f}".rstrip("0").rstrip("."))
        if spec.show_legend and len(series) > 1 and chart_type not in {"pie", "donut", "heatmap"}:
            axis.legend(frameon=False, loc="best")
        axis.grid(axis="y", color="#E9EEF5", linewidth=0.7)
        axis.spines[["top", "right"]].set_visible(False)
        svg = io.BytesIO()
        figure.savefig(svg, format="svg", transparent=False)
        png = io.BytesIO()
        figure.savefig(png, format="png", dpi=300, facecolor="white")
        plt.close(figure)
        image = Image.open(io.BytesIO(png.getvalue())).convert("RGB")
        image.thumbnail((600, 360), Image.Resampling.LANCZOS)
        thumb = io.BytesIO()
        image.save(thumb, format="PNG", optimize=True)
        if len(png.getvalue()) > 64 * 1024 * 1024:
            raise ValueError("CHART_RENDER_SIZE_LIMIT")
        return ChartFiles(svg=svg.getvalue(), png=png.getvalue(), thumbnail_png=thumb.getvalue())

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("CHART_NUMERIC_VALUE_INVALID") from None
        if not math.isfinite(number):
            raise ValueError("CHART_NUMERIC_VALUE_INVALID")
        return number
