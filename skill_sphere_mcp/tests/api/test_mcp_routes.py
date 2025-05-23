# pylint: disable=redefined-outer-name
"""Tests for MCP routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import HTTPException
from neo4j import AsyncSession

from skill_sphere_mcp.api import mcp_routes
from skill_sphere_mcp.api.mcp_routes import (
    InitializeRequest,
    InitializeResponse,
    ResourceRequest,
    ToolRequest,
    dispatch_tool,
    get_resource,
    initialize,
    list_resources,
)

# Test data
MOCK_TOKEN = "test_token"
MOCK_SKILL_ID = "123"
MOCK_RESOURCE_TYPE = "skills.node"
MOCK_TOOL_NAME = "skill.match_role"

# HTTP status codes
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500
HTTP_NOT_IMPLEMENTED = 501


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock Neo4j session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_token() -> str:
    """Create a mock PAT token."""
    return MOCK_TOKEN


@pytest.mark.asyncio
async def test_initialize(mock_token: str) -> None:
    """Test MCP initialization endpoint."""
    request = InitializeRequest(protocol_version="1.0")
    response = await initialize(request, mock_token)

    assert isinstance(response, InitializeResponse)
    assert response.protocol_version == "1.0"
    assert "resources" in response.capabilities
    assert "tools" in response.capabilities
    assert isinstance(response.instructions, str)


@pytest.mark.asyncio
async def test_list_resources(mock_token: str) -> None:
    """Test resource listing endpoint."""
    resources = await list_resources(mock_token)
    assert isinstance(resources, list)
    assert len(resources) > 0
    assert all(isinstance(r, str) for r in resources)


@pytest.mark.asyncio
async def test_get_resource_success(mock_session: AsyncMock, mock_token: str) -> None:
    """Test successful resource retrieval."""
    mock_record = {
        "n": MagicMock(id=123, labels=["Skill"], properties={"name": "Python"}),
        "labels": ["Skill"],
        "props": {"name": "Python"},
    }
    mock_session.run.return_value.single.return_value = mock_record

    request = ResourceRequest(
        resource_type=MOCK_RESOURCE_TYPE, resource_id=MOCK_SKILL_ID
    )
    response = await get_resource(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "n" in response
    assert "labels" in response
    assert "props" in response


@pytest.mark.asyncio
async def test_get_resource_not_found(mock_session: AsyncMock, mock_token: str) -> None:
    """Test resource retrieval with non-existent resource."""
    mock_session.run.return_value.single.return_value = None

    request = ResourceRequest(
        resource_type=MOCK_RESOURCE_TYPE, resource_id=MOCK_SKILL_ID
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_resource(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_NOT_FOUND


@pytest.mark.asyncio
async def test_get_resource_invalid_type(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test resource retrieval with invalid resource type."""
    request = ResourceRequest(resource_type="invalid.type", resource_id=MOCK_SKILL_ID)
    with pytest.raises(HTTPException) as exc_info:
        await get_resource(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_get_resource_invalid_id_format(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test resource retrieval with invalid ID format."""
    request = ResourceRequest(
        resource_type=MOCK_RESOURCE_TYPE, resource_id="not_a_number"
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_resource(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_get_resource_database_error(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test resource retrieval with database error."""
    mock_session.run.side_effect = Exception("Database error")
    request = ResourceRequest(
        resource_type=MOCK_RESOURCE_TYPE, resource_id=MOCK_SKILL_ID
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_resource(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_SERVER_ERROR


@pytest.mark.asyncio
async def test_dispatch_tool_success(mock_session: AsyncMock, mock_token: str) -> None:
    """Test successful tool dispatch."""
    parameters = {
        "required_skills": ["Python", "FastAPI"],
        "years_experience": {"Python": 5},
    }
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)

    with patch("skill_sphere_mcp.api.mcp_routes.match_role") as mock_match_role:
        mock_match_role.return_value = {
            "match_score": 0.8,
            "skill_gaps": [],
            "matching_skills": [],
        }
        response = await dispatch_tool(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "match_score" in response
    assert "skill_gaps" in response
    assert "matching_skills" in response


@pytest.mark.asyncio
async def test_dispatch_tool_invalid_name(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test tool dispatch with invalid tool name."""
    request = ToolRequest(tool_name="invalid.tool", parameters={})
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_dispatch_tool_invalid_params(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test tool dispatch with invalid parameters."""
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters={})
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_explain_match_tool(mock_session: AsyncMock, mock_token: str) -> None:
    """Test explain match tool handler."""
    parameters = {
        "skill_id": "123",
        "role_requirement": "Python developer with 5 years experience",
    }
    request = ToolRequest(tool_name="skill.explain_match", parameters=parameters)

    with patch("skill_sphere_mcp.api.mcp_routes.explain_match") as mock_explain:
        mock_explain.return_value = {
            "explanation": "Skill matches requirement",
            "evidence": [{"type": "experience", "details": "5 years"}],
        }
        response = await dispatch_tool(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "explanation" in response
    assert "evidence" in response


@pytest.mark.asyncio
async def test_generate_cv_tool(mock_session: AsyncMock, mock_token: str) -> None:
    """Test CV generation tool handler."""
    parameters = {
        "target_keywords": ["Python", "FastAPI"],
        "format": "markdown",
    }
    request = ToolRequest(tool_name="cv.generate", parameters=parameters)

    with patch("skill_sphere_mcp.api.mcp_routes.generate_cv") as mock_generate:
        mock_generate.return_value = {
            "content": "# Professional CV",
            "format": "markdown",
        }
        response = await dispatch_tool(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "content" in response
    assert "format" in response


@pytest.mark.asyncio
async def test_graph_search_tool(mock_session: AsyncMock, mock_token: str) -> None:
    """Test graph search tool handler."""
    parameters = {
        "query": "Python developer",
        "top_k": 5,
    }
    request = ToolRequest(tool_name="graph.search", parameters=parameters)

    with patch("skill_sphere_mcp.api.mcp_routes.graph_search") as mock_search:
        mock_search.return_value = {
            "results": [
                {
                    "node_id": "1",
                    "score": 0.8,
                    "labels": ["Skill"],
                    "properties": {"name": "Python"},
                }
            ]
        }
        response = await dispatch_tool(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "results" in response
    assert isinstance(response["results"], list)


@pytest.mark.asyncio
async def test_tool_handler_error(mock_session: AsyncMock, mock_token: str) -> None:
    """Test error handling in tool handlers."""
    parameters = {"required_skills": ["Python"]}
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)

    with patch("skill_sphere_mcp.api.mcp_routes.match_role") as mock_match_role:
        mock_match_role.side_effect = Exception("Tool execution error")
        with pytest.raises(HTTPException) as exc_info:
            await dispatch_tool(request, mock_session, mock_token)
        assert exc_info.value.status_code == HTTP_SERVER_ERROR


@pytest.mark.asyncio
async def test_initialize_invalid_version(mock_token: str) -> None:
    """Test MCP initialization with invalid version."""
    request = InitializeRequest(protocol_version="0.9")
    response = await initialize(request, mock_token)
    assert response.protocol_version == "1.0"  # Should return supported version


@pytest.mark.asyncio
async def test_get_resource_skills_relation(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test resource retrieval for skills relation type."""
    mock_record = {
        "r": MagicMock(id=123, type="RELATES_TO", properties={"weight": 0.8}),
        "type": "RELATES_TO",
        "props": {"weight": 0.8},
        "source_id": 1,
        "target_id": 2,
    }
    mock_session.run.return_value.single.return_value = mock_record

    request = ResourceRequest(
        resource_type="skills.relation", resource_id=MOCK_SKILL_ID
    )
    response = await get_resource(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "r" in response
    assert "type" in response
    assert "props" in response
    assert "source_id" in response
    assert "target_id" in response


@pytest.mark.asyncio
async def test_get_resource_profiles_detail(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test resource retrieval for profiles detail type."""
    mock_record = {
        "p": MagicMock(id=123, labels=["Profile"], properties={"name": "John"}),
        "labels": ["Profile"],
        "props": {"name": "John"},
        "relationships": [
            {
                "rel": MagicMock(type="HAS_SKILL"),
                "node": MagicMock(id=1, labels=["Skill"]),
            }
        ],
    }
    mock_session.run.return_value.single.return_value = mock_record

    request = ResourceRequest(
        resource_type="profiles.detail", resource_id=MOCK_SKILL_ID
    )
    response = await get_resource(request, mock_session, mock_token)

    assert isinstance(response, dict)
    assert "p" in response
    assert "labels" in response
    assert "props" in response
    assert "relationships" in response
    assert isinstance(response["relationships"], list)


@pytest.mark.asyncio
async def test_explain_match_tool_invalid_params(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test explain match tool with invalid parameters."""
    parameters = {
        "skill_id": "123",
        # Missing required role_requirement
    }
    request = ToolRequest(tool_name="skill.explain_match", parameters=parameters)

    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_generate_cv_tool_invalid_format(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test CV generation tool with invalid format."""
    parameters = {
        "target_keywords": ["Python"],
        "format": "invalid_format",  # Invalid format
    }
    request = ToolRequest(tool_name="cv.generate", parameters=parameters)

    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_graph_search_tool_invalid_top_k(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test graph search tool with invalid top_k value."""
    parameters = {
        "query": "Python developer",
        "top_k": 0,  # Invalid top_k value
    }
    request = ToolRequest(tool_name="graph.search", parameters=parameters)

    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_match_role_tool_empty_skills(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test match role tool with empty skills list."""
    parameters: dict = {
        "required_skills": [],  # Empty skills list
        "years_experience": {},
    }
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)

    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_match_role_tool_invalid_experience(
    mock_session: AsyncMock, mock_token: str
) -> None:
    """Test match role tool with invalid experience format."""
    parameters = {
        "required_skills": ["Python"],
        "years_experience": {"Python": "invalid"},  # Invalid experience value
    }
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)

    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request, mock_session, mock_token)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_match_role_success() -> None:
    """Test match_role returns expected result."""
    params = {"required_skills": ["Python"], "years_experience": {}}
    mock_session = AsyncMock()
    # Simulate DB returning a skill node
    mock_skill = {"s": {"name": "Python"}, "relationships": []}
    mock_session.run.return_value.__aiter__.return_value = [mock_skill]
    result = await mcp_routes.match_role(params, mock_session)
    assert "match_score" in result
    assert result["match_score"] == pytest.approx(1.0)
    assert result["skill_gaps"] == []
    assert result["matching_skills"][0]["name"] == "Python"


@pytest.mark.asyncio
async def test_match_role_invalid_params() -> None:
    """Test match_role with invalid parameters raises HTTPException."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await mcp_routes.match_role({}, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_explain_match_success() -> None:
    """Test explain_match returns expected result."""
    params = {"skill_id": "1", "role_requirement": "Python dev"}
    mock_session = AsyncMock()
    # Simulate DB returning a skill node with evidence
    mock_record = {
        "s": {"name": "Python"},
        "evidence": [
            {"rel": MagicMock(type="HAS_SKILL"), "target": {"name": "FastAPI"}}
        ],
    }
    mock_session.run.return_value.single.return_value = mock_record
    result = await mcp_routes.explain_match(params, mock_session)
    assert "explanation" in result
    assert "evidence" in result
    assert result["evidence"][0]["type"] == "HAS_SKILL"


@pytest.mark.asyncio
async def test_explain_match_invalid_params() -> None:
    """Test explain_match with invalid parameters raises HTTPException."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await mcp_routes.explain_match({}, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_explain_match_value_error() -> None:
    """Test explain_match with invalid skill_id format raises HTTPException."""
    params = {"skill_id": "not_a_number", "role_requirement": "Python dev"}
    mock_session = AsyncMock()
    mock_session.run.side_effect = ValueError()
    with pytest.raises(HTTPException) as exc_info:
        await mcp_routes.explain_match(params, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_generate_cv_success() -> None:
    """Test generate_cv returns markdown CV."""
    params = {"target_keywords": ["Python"], "format": "markdown"}
    mock_session = AsyncMock()
    mock_record = {"p": {"name": "John"}, "skills": [{"skill": {"name": "Python"}}]}
    mock_session.run.return_value.single.return_value = mock_record
    result = await mcp_routes.generate_cv(params, mock_session)
    assert result["format"] == "markdown"
    assert "# John" in result["content"]
    assert "- Python" in result["content"]


@pytest.mark.asyncio
async def test_generate_cv_invalid_params() -> None:
    """Test generate_cv with invalid parameters raises HTTPException."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await mcp_routes.generate_cv({}, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_generate_cv_profile_not_found() -> None:
    """Test generate_cv when profile not found raises HTTPException."""
    params = {"target_keywords": ["Python"], "format": "markdown"}
    mock_session = AsyncMock()
    mock_session.run.return_value.single.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await mcp_routes.generate_cv(params, mock_session)
    assert exc_info.value.status_code == HTTP_NOT_FOUND


@pytest.mark.asyncio
async def test_generate_cv_format_not_implemented() -> None:
    """Test generate_cv with unsupported format raises HTTPException."""
    params = {"target_keywords": ["Python"], "format": "pdf"}
    mock_session = AsyncMock()
    mock_record = {"p": {"name": "John"}, "skills": []}
    mock_session.run.return_value.single.return_value = mock_record
    with pytest.raises(HTTPException) as exc_info:
        await mcp_routes.generate_cv(params, mock_session)
    assert exc_info.value.status_code == HTTP_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_graph_search_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test graph_search returns results."""
    params = {"query": "Python", "top_k": 1}
    mock_session = AsyncMock()
    # Patch embeddings.search to return a fake result
    monkeypatch.setattr(
        mcp_routes.embeddings,
        "search",
        AsyncMock(
            return_value=[
                {
                    "node_id": "1",
                    "score": 0.9,
                    "labels": ["Skill"],
                    "properties": {"name": "Python"},
                }
            ]
        ),
    )

    # Patch MODEL.encode to return a numpy array
    class DummyModel:
        """Mock model class for testing graph search functionality."""

        def encode(self, _query: str) -> object:
            """Mock encode method that returns a dummy tensor."""

            class DummyTensor:
                """Mock tensor class that returns a numpy array of ones."""

                def numpy(self) -> np.ndarray:
                    """Return a numpy array of ones with shape (128,)."""
                    return np.ones(128)

            return DummyTensor()

    monkeypatch.setattr(mcp_routes, "MODEL", DummyModel())
    result = await mcp_routes.graph_search(params, mock_session)
    assert "results" in result
    assert result["results"][0]["node_id"] == "1"


@pytest.mark.asyncio
async def test_graph_search_importerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test graph_search falls back to random embedding if MODEL is None."""
    params = {"query": "Python", "top_k": 1}
    mock_session = AsyncMock()
    monkeypatch.setattr(
        mcp_routes.embeddings,
        "search",
        AsyncMock(
            return_value=[
                {
                    "node_id": "1",
                    "score": 0.9,
                    "labels": ["Skill"],
                    "properties": {"name": "Python"},
                }
            ]
        ),
    )
    monkeypatch.setattr(mcp_routes, "MODEL", None)
    result = await mcp_routes.graph_search(params, mock_session)
    assert "results" in result
    assert result["results"][0]["node_id"] == "1"
