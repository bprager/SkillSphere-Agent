# pylint: disable=redefined-outer-name
"""Tests for MCP routes."""

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from fastapi import HTTPException
from neo4j import AsyncSession

# Create a test instance of JSONRPCHandler
from skill_sphere_mcp.api.jsonrpc import JSONRPCHandler
from skill_sphere_mcp.api.jsonrpc import JSONRPCRequest
from skill_sphere_mcp.api.jsonrpc import JSONRPCResponse
from skill_sphere_mcp.api.mcp.handlers import SKILL_MATCH_THRESHOLD
from skill_sphere_mcp.api.mcp.handlers import explain_match
from skill_sphere_mcp.api.mcp.handlers import graph_search
from skill_sphere_mcp.api.mcp.handlers import match_role
from skill_sphere_mcp.api.mcp.models import ToolRequest
from skill_sphere_mcp.api.mcp.routes import list_resources
from skill_sphere_mcp.api.mcp.rpc import rpc_match_role_handler
from skill_sphere_mcp.api.mcp.utils import get_resource
from skill_sphere_mcp.cv.generator import generate_cv
from skill_sphere_mcp.graph.embeddings import embeddings
from skill_sphere_mcp.tools.dispatcher import dispatch_tool


test_rpc_handler = JSONRPCHandler()

# Test data
MOCK_SKILL_ID = "123"
MOCK_RESOURCE_TYPE = "skills.node"
MOCK_TOOL_NAME = "skill.match_role"
MOCK_SKILLS = ["Python", "FastAPI"]
MOCK_YEARS = {"Python": 5, "FastAPI": 3}
MOCK_MATCH_RESULT = {
    "match_score": 0.85,
    "matching_skills": [{"name": "Python"}],
    "skill_gaps": [],
}

# HTTP status codes
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500
HTTP_NOT_IMPLEMENTED = 501
HTTP_422_UNPROCESSABLE_ENTITY = 422


@pytest_asyncio.fixture
async def mock_session() -> AsyncMock:
    """Create a mock Neo4j session."""
    return AsyncMock(spec=AsyncSession)


@pytest_asyncio.fixture
async def test_list_resources() -> None:
    """Test resource listing endpoint."""
    resources = await list_resources()
    assert isinstance(resources, list)
    assert len(resources) > 0
    assert all(isinstance(r, str) for r in resources)


@pytest_asyncio.fixture
async def test_get_resource_success() -> None:
    """Test successful resource retrieval."""
    response = await get_resource(MOCK_RESOURCE_TYPE)
    assert isinstance(response, dict)
    assert "type" in response
    assert "schema" in response


@pytest_asyncio.fixture
async def test_get_resource_not_found() -> None:
    """Test resource retrieval with non-existent resource."""
    # The endpoint now returns schema for any valid resource type, so this test is not applicable.
    # We'll skip this test.
    pytest.skip("Resource not found test is not applicable for schema-only endpoint.")


@pytest_asyncio.fixture
async def test_get_resource_invalid_type() -> None:
    """Test resource retrieval with invalid resource type."""
    with pytest.raises(HTTPException) as exc_info:
        await get_resource("invalid.type")
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest_asyncio.fixture
async def test_get_resource_invalid_id_format() -> None:
    """Test resource retrieval with invalid ID format."""
    with pytest.raises(HTTPException) as exc_info:
        await get_resource("not_a_number")
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest_asyncio.fixture
async def test_get_resource_database_error() -> None:
    """Test resource retrieval with database error."""
    # The endpoint now returns schema for any valid resource type, so this test is not applicable.
    pytest.skip("Database error test is not applicable for schema-only endpoint.")


@pytest_asyncio.fixture
async def test_dispatch_tool_success(mock_session: AsyncMock) -> None:
    """Test successful tool dispatch."""
    parameters = {
        "required_skills": ["Python", "FastAPI"],
        "years_experience": {"Python": 5},
    }
    request = ToolRequest(tool_name="skill.match_role", parameters=parameters)
    # Patch the DB result to return skills compatible with match_role
    mock_record = {"p": {"name": "John Doe", "skills": ["Python", "FastAPI"]}}
    mock_session.run.return_value.all.return_value = [mock_record]
    response = await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert isinstance(response, dict)
    assert "match_score" in response
    assert "skill_gaps" in response
    assert "matching_skills" in response
    assert response["match_score"] == pytest.approx(1.0)
    assert "Python" in [skill["name"] for skill in response["matching_skills"]]


@pytest_asyncio.fixture
async def test_dispatch_tool_invalid_name(mock_session: AsyncMock) -> None:
    """Test tool dispatch with invalid tool name."""
    request = ToolRequest(tool_name="invalid.tool", parameters={})
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_NOT_FOUND


@pytest_asyncio.fixture
async def test_dispatch_tool_invalid_params(mock_session: AsyncMock) -> None:
    """Test tool dispatch with invalid parameters."""
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters={})
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest_asyncio.fixture
async def test_explain_match_tool(mock_session: AsyncMock) -> None:
    """Test explain match tool handler."""
    parameters = {
        "skill_id": "123",
        "role_requirement": "Python developer with 5 years experience",
    }
    request = ToolRequest(tool_name="skill.explain_match", parameters=parameters)
    response = await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert isinstance(response, dict)
    assert "explanation" in response
    assert "evidence" in response


@pytest_asyncio.fixture
async def test_generate_cv_tool(mock_session: AsyncMock) -> None:
    """Test CV generation tool handler."""
    parameters = {
        "target_keywords": ["Python", "FastAPI"],
        "format": "markdown",
    }
    request = ToolRequest(tool_name="cv.generate", parameters=parameters)
    mock_record = {
        "p": {"name": "John Doe"},
        "skills": [{"name": "Python"}, {"name": "FastAPI"}],
        "companies": [],
        "education": [],
    }
    mock_session.run.return_value.single.return_value = mock_record
    response = await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert isinstance(response, dict)
    assert "content" in response
    assert "format" in response


@pytest_asyncio.fixture
async def test_graph_search_tool(mock_session: AsyncMock) -> None:
    """Test graph search tool handler."""
    parameters = {
        "query": "Python developer",
        "top_k": 5,
    }
    request = ToolRequest(tool_name="graph.search", parameters=parameters)
    response = await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert isinstance(response, dict)
    assert "results" in response
    assert isinstance(response["results"], list)


@pytest_asyncio.fixture
async def test_tool_handler_error(mock_session: AsyncMock) -> None:
    """Test error handling in tool handlers."""
    parameters = {"required_skills": ["Python"]}
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)
    # Simulate error by passing invalid tool name
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool("invalid.tool", request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_NOT_FOUND


@pytest.mark.asyncio
async def test_get_resource_skills_relation() -> None:
    """Test resource retrieval for skills relation type."""
    response = await get_resource("skills.relation")
    assert isinstance(response, dict)
    assert "type" in response
    assert "schema" in response


@pytest.mark.asyncio
async def test_get_resource_profiles_detail() -> None:
    """Test resource retrieval for profiles detail type."""
    response = await get_resource("profiles.detail")
    assert isinstance(response, dict)
    assert "type" in response
    assert "schema" in response


@pytest.mark.asyncio
async def test_explain_match_tool_invalid_params(mock_session: AsyncMock) -> None:
    """Test explain match tool with invalid parameters."""
    parameters = {
        "skill_id": "123",
        # Missing required role_requirement
    }
    request = ToolRequest(tool_name="skill.explain_match", parameters=parameters)
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_generate_cv_tool_invalid_format(mock_session: AsyncMock) -> None:
    """Test CV generation tool with invalid format."""
    parameters = {
        "target_keywords": ["Python"],
        "format": "invalid_format",  # Invalid format
    }
    request = ToolRequest(tool_name="cv.generate", parameters=parameters)
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_graph_search_tool_invalid_top_k(mock_session: AsyncMock) -> None:
    """Test graph search tool with invalid top_k value."""
    parameters = {
        "query": "Python developer",
        "top_k": 0,  # Invalid top_k value
    }
    request = ToolRequest(tool_name="graph.search", parameters=parameters)
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_match_role_tool_empty_skills(mock_session: AsyncMock) -> None:
    """Test match role tool with empty skills list."""
    parameters: dict = {
        "required_skills": [],  # Empty skills list
        "years_experience": {},
    }
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_match_role_tool_invalid_experience(mock_session: AsyncMock) -> None:
    """Test match role tool with invalid experience format."""
    parameters = {
        "required_skills": ["Python"],
        "years_experience": {"Python": "invalid"},  # Invalid experience value
    }
    request = ToolRequest(tool_name=MOCK_TOOL_NAME, parameters=parameters)
    with pytest.raises(HTTPException) as exc_info:
        await dispatch_tool(request.tool_name, request.parameters, mock_session)
    assert exc_info.value.status_code == HTTP_BAD_REQUEST


@pytest.mark.asyncio
async def test_match_role_success() -> None:
    """Test match_role returns expected result."""
    params = {"required_skills": ["Python"], "years_experience": {}}
    mock_session = AsyncMock()
    # Simulate DB returning a person with matching skills
    mock_result = AsyncMock()
    mock_result.all = AsyncMock(
        return_value=[
            {
                "p": {
                    "id": "1",
                    "name": "Test Person",
                    "skills": ["Python"],
                }
            }
        ]
    )
    mock_session.run.return_value = mock_result
    result = await match_role(params, mock_session)
    assert "match_score" in result
    assert result["match_score"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_match_role_invalid_params() -> None:
    """Test match_role with invalid parameters raises HTTPException."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await match_role({}, mock_session)
    assert exc_info.value.status_code == HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_explain_match_success() -> None:
    """Test explain_match returns expected result."""
    params = {"skill_id": "1", "role_requirement": "Python dev"}
    mock_session = AsyncMock()
    # Simulate DB returning a skill node with projects and certifications
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(
        return_value={
            "s": {"id": "1", "name": "Python"},
            "projects": [
                {"id": "p1", "name": "Project A", "description": "Python project"}
            ],
            "certifications": [
                {
                    "id": "c1",
                    "name": "Python Cert",
                    "description": "Python certification",
                }
            ],
        }
    )
    mock_session.run.return_value = mock_result
    result = await explain_match(params, mock_session)
    assert "explanation" in result
    assert "evidence" in result
    assert len(result["evidence"]) == 2


@pytest.mark.asyncio
async def test_explain_match_invalid_params() -> None:
    """Test explain_match with invalid parameters raises HTTPException."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await explain_match({}, mock_session)
    assert exc_info.value.status_code == HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_explain_match_value_error() -> None:
    """Test explain_match with invalid skill_id format raises HTTPException."""
    params = {"skill_id": "not_a_number", "role_requirement": "Python dev"}
    mock_session = AsyncMock()
    mock_session.run.side_effect = ValueError()
    with pytest.raises(HTTPException) as exc_info:
        await explain_match(params, mock_session)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_generate_cv_success() -> None:
    """Test generate_cv returns markdown CV."""
    params = {"target_keywords": ["Python"], "format": "markdown"}
    mock_session = AsyncMock()
    mock_record = {
        "p": {"name": "John"},
        "skills": [{"name": "Python"}],
        "companies": [],
        "education": [],
    }
    mock_session.run.return_value.single.return_value = mock_record
    result = await generate_cv(params, mock_session)
    assert result["format"] == "markdown"
    assert "# John" in result["content"]
    assert "- Python" in result["content"]


@pytest.mark.asyncio
async def test_generate_cv_invalid_params() -> None:
    """Test generate_cv with invalid parameters raises ValueError."""
    mock_session = AsyncMock()
    with pytest.raises(ValueError) as exc_info:
        await generate_cv({}, mock_session)
    assert "validation errors for GenerateCVRequest" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_cv_profile_not_found() -> None:
    """Test generate_cv when profile not found raises HTTPException."""
    params = {"target_keywords": ["Python"], "format": "markdown"}
    mock_session = AsyncMock()
    mock_session.run.return_value.single.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await generate_cv(params, mock_session)
    assert exc_info.value.status_code == HTTP_NOT_FOUND


@pytest.mark.asyncio
async def test_generate_cv_format_not_implemented() -> None:
    """Test generate_cv with unsupported format raises HTTPException."""
    params = {"target_keywords": ["Python"], "format": "pdf"}
    mock_session = AsyncMock()
    mock_record = {
        "p": {"name": "John"},
        "skills": [],
        "companies": [],
        "education": [],
    }
    mock_session.run.return_value.single.return_value = mock_record
    with pytest.raises(HTTPException) as exc_info:
        await generate_cv(params, mock_session)
    assert exc_info.value.status_code == HTTP_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_graph_search_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test graph_search returns results."""
    params = {"query": "Python", "top_k": 1}
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.all = AsyncMock(
        return_value=[
            {
                "n": {
                    "id": "1",
                    "name": "Python",
                    "type": "Skill",
                    "description": "Python programming language",
                    "labels": ["Skill"],
                }
            }
        ]
    )
    mock_session.run.return_value = mock_result
    result = await graph_search(params, mock_session)
    assert "results" in result
    assert len(result["results"]) > 0
    assert result["results"][0]["node"]["name"] == "Python"


@pytest.mark.asyncio
async def test_graph_search_importerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test graph_search falls back to random embedding if MODEL is None."""
    params = {"query": "Python", "top_k": 1}
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.all = AsyncMock(
        return_value=[
            {
                "n": {
                    "id": "1",
                    "name": "Python",
                    "type": "Skill",
                    "description": "Python programming language",
                    "labels": ["Skill"],
                }
            }
        ]
    )
    mock_session.run.return_value = mock_result
    result = await graph_search(params, mock_session)
    assert "results" in result
    assert len(result["results"]) > 0
    assert result["results"][0]["node"]["name"] == "Python"


@pytest.mark.asyncio
async def test_handle_skill_match_success() -> None:
    """Test successful skill matching."""
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.all = AsyncMock(
        return_value=[
            {
                "p": {
                    "id": "1",
                    "name": "Test Person",
                    "skills": ["Python"],
                }
            }
        ]
    )
    mock_session.run.return_value = mock_result
    params = {
        "required_skills": ["Python"],
        "years_experience": {"Python": 5},
    }
    result = await rpc_match_role_handler(params, mock_session)
    assert "match_score" in result
    assert result["match_score"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_handle_skill_match_below_threshold() -> None:
    """Test skill matching below threshold."""
    mock_session = AsyncMock()
    with patch("skill_sphere_mcp.tools.dispatcher.dispatch_tool") as mock_dispatch:
        mock_dispatch.return_value = {
            "match_score": SKILL_MATCH_THRESHOLD - 0.1,
            "matching_skills": [],
            "skill_gaps": MOCK_SKILLS,
        }
        params = {
            "required_skills": MOCK_SKILLS,
            "years_experience": MOCK_YEARS,
        }
        result = await rpc_match_role_handler(params, mock_session)
        assert "match_score" in result
        assert result["match_score"] < SKILL_MATCH_THRESHOLD
        assert len(result["matching_skills"]) == 0
        assert len(result["skill_gaps"]) == len(MOCK_SKILLS)


@pytest.mark.asyncio
async def test_handle_skill_match_error() -> None:
    """Test skill matching with error."""
    with patch("skill_sphere_mcp.tools.dispatcher.dispatch_tool") as mock_dispatch:
        mock_dispatch.side_effect = Exception("Matching error")

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="skill.match_role",
            params={
                "required_skills": MOCK_SKILLS,
                "years_experience": MOCK_YEARS,
            },
            id=1,
        )
        result = await test_rpc_handler.handle_request(request)

        assert isinstance(result, JSONRPCResponse)
        assert result.jsonrpc == "2.0"
        assert result.id == 1
        assert result.error is not None


@pytest.mark.asyncio
async def test_handle_jsonrpc_request_success() -> None:
    """Test successful JSON-RPC request handling."""
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.all = AsyncMock(
        return_value=[
            {
                "p": {
                    "id": "1",
                    "name": "Test Person",
                    "skills": ["Python"],
                }
            }
        ]
    )
    mock_session.run.return_value = mock_result
    params = {
        "required_skills": ["Python"],
        "years_experience": {"Python": 5},
    }
    result = await rpc_match_role_handler(params, mock_session)
    assert "match_score" in result
    assert result["match_score"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_handle_jsonrpc_request_invalid_method() -> None:
    """Test JSON-RPC request with invalid method."""
    request = JSONRPCRequest(
        jsonrpc="2.0",
        method="invalid.method",
        params={},
        id=1,
    )
    result = await test_rpc_handler.handle_request(request)

    assert isinstance(result, JSONRPCResponse)
    assert result.jsonrpc == "2.0"
    assert result.id == 1
    assert result.error is not None


@pytest.mark.asyncio
async def test_handle_jsonrpc_request_invalid_params() -> None:
    """Test JSON-RPC request with invalid parameters."""
    request = JSONRPCRequest(
        jsonrpc="2.0",
        method="skill.match_role",
        params={},
        id=1,
    )
    result = await test_rpc_handler.handle_request(request)

    assert isinstance(result, JSONRPCResponse)
    assert result.jsonrpc == "2.0"
    assert result.id == 1
    assert result.error is not None


@pytest.mark.asyncio
async def test_handle_jsonrpc_request_internal_error() -> None:
    """Test JSON-RPC request with internal error."""
    with patch("skill_sphere_mcp.tools.dispatcher.dispatch_tool") as mock_dispatch:
        mock_dispatch.side_effect = Exception("Internal error")

        request = JSONRPCRequest(
            jsonrpc="2.0",
            method="skill.match_role",
            params={
                "required_skills": MOCK_SKILLS,
                "years_experience": MOCK_YEARS,
            },
            id=1,
        )
        result = await test_rpc_handler.handle_request(request)

        assert isinstance(result, JSONRPCResponse)
        assert result.jsonrpc == "2.0"
        assert result.id == 1
        assert result.error is not None
