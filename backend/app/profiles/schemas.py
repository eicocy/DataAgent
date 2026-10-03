from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    version: str = '1.0'
    name: str
    category: str
    description: str
    recommended_for: list[str] = Field(default_factory=list)
    example_questions: list[str] = Field(default_factory=list)
    recommended_data: list[str] = Field(default_factory=list)
    intent_keywords: list[str] = Field(default_factory=list)
    expected_metrics: list[str] = Field(default_factory=list)
    expected_dimensions: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    preferred_charts: list[str] = Field(default_factory=list)
    analysis_steps: list[str] = Field(default_factory=list)
    report_sections: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    prompt_context: str = ''
    depth: str = 'STANDARD'
    created_at: str = '2026-10-03'
    required_capabilities: list[str] = Field(default_factory=list)
    availability: Literal['available', 'limited', 'planned'] = 'planned'
    constraints: list[str] = Field(default_factory=list)
    supported_depths: list[str] = Field(default_factory=lambda: ['STANDARD'])
    source: Literal['system', 'session'] = 'system'


class ProfileCategory(BaseModel):
    id: str
    name: str
    description: str
