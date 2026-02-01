"""Unit tests for pattern extraction module.

Tests cover:
- Language detection (AC 2.3.2)
- Framework detection (AC 2.3.5)
- Importance assessment (AC 2.3.6)
- Tag extraction (AC 2.3.2)
- Edge case handling (AC 2.3.3)
- Python AST extraction (AC 2.3.4)
- Enriched content format (AC 2.3.2)

Story: 2.3 - Pattern Extraction Logic
"""

import pytest

from memory.extraction import (
    assess_importance,
    build_enriched_content,
    detect_framework,
    detect_language,
    extract_patterns,
    extract_python_structure,
    extract_tags,
)


class TestLanguageDetection:
    """Test language detection from file extensions (AC 2.3.2)."""

    @pytest.mark.parametrize(
        "ext,expected",
        [
            (".py", "python"),
            (".js", "javascript"),
            (".ts", "typescript"),
            (".jsx", "javascript"),
            (".tsx", "typescript"),
            (".go", "go"),
            (".rs", "rust"),
            (".java", "java"),
            (".kt", "kotlin"),
            (".rb", "ruby"),
            (".php", "php"),
            (".c", "c"),
            (".cpp", "cpp"),
            (".cs", "csharp"),
            (".swift", "swift"),
            (".md", "markdown"),
            (".yaml", "yaml"),
            (".yml", "yaml"),
            (".json", "json"),
            (".html", "html"),
            (".css", "css"),
            (".sql", "sql"),
        ],
    )
    def test_detect_language_known_extensions(self, ext, expected):
        """Known extensions map to correct languages."""
        result = detect_language(f"/path/file{ext}")
        assert result == expected

    def test_detect_language_unknown_extension(self):
        """Unknown extension returns 'unknown'."""
        result = detect_language("/path/file.xyz")
        assert result == "unknown"

    def test_detect_language_case_insensitive(self):
        """Extension matching is case-insensitive."""
        result = detect_language("/path/file.PY")
        assert result == "python"

    def test_detect_language_no_extension(self):
        """File without extension returns 'unknown'."""
        result = detect_language("/path/Makefile")
        assert result == "unknown"


class TestFrameworkDetection:
    """Test framework detection from content (AC 2.3.5)."""

    # Python frameworks
    def test_detect_framework_fastapi(self):
        """FastAPI detected from import statement."""
        content = "from fastapi import FastAPI\n\napp = FastAPI()"
        result = detect_framework(content, "python")
        assert result == "fastapi"

    def test_detect_framework_flask(self):
        """Flask detected from import statement."""
        content = "from flask import Flask\n\napp = Flask(__name__)"
        result = detect_framework(content, "python")
        assert result == "flask"

    def test_detect_framework_django(self):
        """Django detected from import statement."""
        content = "from django.http import HttpResponse"
        result = detect_framework(content, "python")
        assert result == "django"

    def test_detect_framework_pytest(self):
        """Pytest detected from import statement."""
        content = "import pytest\n\ndef test_foo():\n    pass"
        result = detect_framework(content, "python")
        assert result == "pytest"

    # JavaScript/TypeScript frameworks
    def test_detect_framework_react(self):
        """React detected from import statement."""
        content = "import React from 'react';\n\nfunction App() {}"
        result = detect_framework(content, "javascript")
        assert result == "react"

    def test_detect_framework_nextjs(self):
        """Next.js detected from import statement."""
        content = 'import { NextPage } from "next";'
        result = detect_framework(content, "typescript")
        assert result == "nextjs"

    def test_detect_framework_vue(self):
        """Vue detected from import statement."""
        content = "import { createApp } from 'vue';"
        result = detect_framework(content, "javascript")
        assert result == "vue"

    def test_detect_framework_express(self):
        """Express detected from function call."""
        content = "const app = express();"
        result = detect_framework(content, "javascript")
        assert result == "express"

    def test_detect_framework_general_no_match(self):
        """No framework match returns 'general'."""
        content = "print('hello world')"
        result = detect_framework(content, "python")
        assert result == "general"


class TestImportanceAssessment:
    """Test importance assessment (AC 2.3.6)."""

    def test_assess_importance_high_class_definition(self):
        """Class definition triggers high importance."""
        content = "class UserAuth:\n    def __init__(self):\n        pass"
        result = assess_importance(content, "/path/auth.py")
        assert result == "high"

    def test_assess_importance_high_async_def(self):
        """Async function triggers high importance."""
        content = "async def fetch_data():\n    await something()"
        result = assess_importance(content, "/path/service.py")
        assert result == "high"

    def test_assess_importance_high_try_block(self):
        """Try/except triggers high importance."""
        content = "def process():\n    try:\n        do_something()\n    except Exception:\n        pass"
        result = assess_importance(content, "/path/handler.py")
        assert result == "high"

    def test_assess_importance_high_decorator(self):
        """Decorator triggers high importance."""
        content = "@dataclass\nclass Config:\n    value: str"
        result = assess_importance(content, "/path/config.py")
        assert result == "high"

    def test_assess_importance_high_file_path_auth(self):
        """Auth in file path triggers high importance."""
        content = "def authenticate_user():\n    pass"
        result = assess_importance(content, "/app/auth/handler.py")
        assert result == "high"

    def test_assess_importance_low_short_content(self):
        """Short content (<50 chars) triggers low importance."""
        content = "x = 1"
        result = assess_importance(content, "/path/file.py")
        assert result == "low"

    def test_assess_importance_low_few_lines(self):
        """Few lines (<3) triggers low importance."""
        content = "a = 1\nb = 2"
        result = assess_importance(content, "/path/file.py")
        assert result == "low"

    def test_assess_importance_low_test_file(self):
        """Test file path triggers low importance."""
        content = "def test_something():\n    assert True"
        result = assess_importance(content, "/tests/test_feature.py")
        assert result == "low"

    def test_assess_importance_normal_default(self):
        """Standard code gets normal importance."""
        content = "def calculate_total(items):\n    total = 0\n    for item in items:\n        total += item.price\n    return total"
        result = assess_importance(content, "/app/utils.py")
        assert result == "normal"


class TestTagExtraction:
    """Test tag extraction (AC 2.3.2)."""

    def test_extract_tags_includes_language(self):
        """Tags always include language."""
        content = "print('hello')"
        result = extract_tags(content, "python", "general")
        assert "python" in result

    def test_extract_tags_includes_framework(self):
        """Tags include framework when not 'general'."""
        content = "from fastapi import FastAPI"
        result = extract_tags(content, "python", "fastapi")
        assert "fastapi" in result

    def test_extract_tags_async_pattern(self):
        """Async code gets 'async' tag."""
        content = "async def fetch():\n    await call()"
        result = extract_tags(content, "python", "general")
        assert "async" in result

    def test_extract_tags_testing_pattern(self):
        """Test code gets 'testing' tag."""
        content = "def test_feature():\n    assert True"
        result = extract_tags(content, "python", "pytest")
        assert "testing" in result

    def test_extract_tags_api_pattern(self):
        """API code gets 'api' tag."""
        content = "@app.get('/api/users')\ndef get_users():\n    pass"
        result = extract_tags(content, "python", "fastapi")
        assert "api" in result

    def test_extract_tags_config_pattern(self):
        """Config code gets 'config' tag."""
        content = "DATABASE_CONFIG = {'host': 'localhost'}"
        result = extract_tags(content, "python", "general")
        assert "config" in result

    def test_extract_tags_error_handling_pattern(self):
        """Error handling gets 'error-handling' tag."""
        content = "try:\n    risky()\nexcept Exception:\n    handle()"
        result = extract_tags(content, "python", "general")
        assert "error-handling" in result


class TestEnrichedContentBuilder:
    """Test enriched content format (AC 2.3.2)."""

    def test_build_enriched_content_with_framework(self):
        """Enriched content includes framework in header."""
        content = "def hello(): pass"
        result = build_enriched_content(content, "/app/main.py", "python", "fastapi")
        assert result.startswith("[python/fastapi] /app/main.py\n\n")
        assert "def hello(): pass" in result

    def test_build_enriched_content_without_framework(self):
        """Enriched content omits framework when 'general'."""
        content = "const x = 1;"
        result = build_enriched_content(
            content, "/app/util.js", "javascript", "general"
        )
        assert result.startswith("[javascript] /app/util.js\n\n")
        assert "const x = 1;" in result

    def test_build_enriched_content_preserves_content(self):
        """Enriched content preserves original content exactly."""
        content = "line1\nline2\nline3"
        result = build_enriched_content(content, "/file.py", "python", "general")
        assert content in result


class TestPythonASTExtraction:
    """Test Python AST extraction (AC 2.3.4)."""

    def test_extract_python_structure_functions(self):
        """Extracts function definitions."""
        code = "def hello(name: str) -> str:\n    return f'Hello {name}'"
        result = extract_python_structure(code)
        assert result is not None
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "hello"
        assert result["functions"][0]["args"] == ["name"]

    def test_extract_python_structure_returns_annotation(self):
        """Extracts return type annotations (AC 2.3.4)."""
        code = "def calculate(x: int, y: int) -> float:\n    return x / y"
        result = extract_python_structure(code)
        assert result is not None
        assert result["functions"][0]["returns"] == "float"

    def test_extract_python_structure_no_returns_annotation(self):
        """Functions without return annotations have None returns."""
        code = "def simple():\n    pass"
        result = extract_python_structure(code)
        assert result is not None
        assert result["functions"][0]["returns"] is None

    def test_extract_python_structure_classes(self):
        """Extracts class definitions."""
        code = """
class Greeter:
    def __init__(self):
        pass
    def greet(self):
        pass
"""
        result = extract_python_structure(code)
        assert result is not None
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "Greeter"
        assert "__init__" in result["classes"][0]["methods"]
        assert "greet" in result["classes"][0]["methods"]

    def test_extract_python_structure_async_functions(self):
        """Detects async functions."""
        code = "async def fetch():\n    await call()"
        result = extract_python_structure(code)
        assert result is not None
        assert result["has_async"] is True
        assert result["functions"][0]["async"] is True

    def test_extract_python_structure_imports(self):
        """Extracts import statements."""
        code = "import os\nfrom pathlib import Path"
        result = extract_python_structure(code)
        assert result is not None
        assert "os" in result["imports"]
        assert "pathlib" in result["imports"]

    def test_extract_python_structure_decorators(self):
        """Extracts decorators."""
        code = "@app.route('/api')\ndef handler():\n    pass"
        result = extract_python_structure(code)
        assert result is not None
        assert len(result["functions"][0]["decorators"]) > 0

    def test_extract_python_structure_malformed_code(self):
        """Returns None for malformed Python code."""
        code = "def broken(:\n    pass"
        result = extract_python_structure(code)
        assert result is None

    def test_extract_python_structure_has_classes_flag(self):
        """Sets has_classes flag correctly."""
        code = "class Foo:\n    pass"
        result = extract_python_structure(code)
        assert result is not None
        assert result["has_classes"] is True

    def test_extract_python_structure_no_classes_flag(self):
        """has_classes is False when no classes."""
        code = "def foo():\n    pass"
        result = extract_python_structure(code)
        assert result is not None
        assert result["has_classes"] is False


class TestEdgeCaseHandling:
    """Test edge case handling (AC 2.3.3)."""

    def test_empty_content_returns_none(self):
        """Empty content returns None."""
        result = extract_patterns("", "/path/file.py")
        assert result is None

    def test_short_content_returns_none(self):
        """Content <10 chars returns None."""
        result = extract_patterns("x = 1", "/path/file.py")
        assert result is None

    def test_binary_file_returns_none(self):
        """Binary content returns None."""
        result = extract_patterns("\x00\x01\x02", "/path/file.bin")
        assert result is None

    def test_unknown_extension_uses_unknown_language(self):
        """Unknown extension uses 'unknown' language."""
        result = extract_patterns("valid content here\nmultiline", "/path/file.xyz")
        assert result is not None
        assert result["language"] == "unknown"

    def test_malformed_python_falls_back(self):
        """Invalid Python syntax doesn't crash."""
        result = extract_patterns("def broken(:\n    pass", "/path/file.py")
        # Should still return result (graceful degradation)
        assert result is not None
        assert result["language"] == "python"


class TestExtractPatternsIntegration:
    """Integration tests for extract_patterns main function."""

    def test_extract_patterns_react_component(self):
        """React component extraction (AC 2.3.2)."""
        content = """
import React from 'react';

function UserProfile() {
    return <div>Profile</div>;
}
"""
        result = extract_patterns(content, "/app/components/UserProfile.tsx")
        assert result is not None
        assert result["language"] == "typescript"
        assert result["framework"] == "react"
        assert "react" in result["tags"]
        assert result["content"].startswith("[typescript/react]")

    def test_extract_patterns_python_class(self):
        """Python class extraction with AST."""
        content = """
class UserAuth:
    def __init__(self, user_id):
        self.user_id = user_id

    async def authenticate(self):
        await verify()
"""
        result = extract_patterns(content, "/app/auth/handler.py")
        assert result is not None
        assert result["language"] == "python"
        assert result["importance"] == "high"  # auth + class + async
        assert "has_classes" in result["tags"]
        assert "has_async" in result["tags"]

    def test_extract_patterns_returns_all_fields(self):
        """Result contains all required fields."""
        content = "def hello():\n    print('world')"
        result = extract_patterns(content, "/app/util.py")
        assert result is not None
        assert "content" in result
        assert "domain" in result
        assert "importance" in result
        assert "tags" in result
        assert "language" in result
        assert "framework" in result
        assert "file_path" in result

    def test_extract_patterns_domain_equals_language(self):
        """Domain field equals language (for future collection filtering)."""
        content = "const x = 1;\nconst y = 2;"
        result = extract_patterns(content, "/app/util.js")
        assert result is not None
        assert result["domain"] == result["language"]
        assert result["domain"] == "javascript"
