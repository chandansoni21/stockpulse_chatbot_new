#!/usr/bin/env python3
"""
Fabric Data Agent External Client

A standalone Python client for calling Microsoft Fabric Data Agents from outside
of the Fabric environment using interactive browser authentication.

Requirements:
- azure-identity
- openai
- python-dotenv (optional, for environment variables)

Usage:
1. Set your TENANT_ID and DATA_AGENT_URL in the script or environment variables
2. Run the script - it will open a browser for authentication
3. The client will fetch a bearer token and make calls to your data agent
"""

import time
import uuid
import json
import re
import os, requests
import sys
import logging
import warnings
from typing import Optional
from openai import OpenAI

from auth_service import acquire_fabric_token

logger = logging.getLogger(__name__)

# Suppress OpenAI Assistants API deprecation warnings
# (Fabric Data Agents don't support the newer Responses API yet)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*Assistants API is deprecated.*"
)

# Optional: Load from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_TIMEOUT = 300
POLL_INTERVAL_SECONDS = 3
HTTP_REQUEST_TIMEOUT = 30.0
VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"

_CHART_QUESTION_PATTERNS = (
    r"\b(?:pie|bar|line|column|area|scatter|donut|doughnut)\s+(?:chart|graph|plot)\b",
    r"\b(?:chart|graph|plot)\s+(?:of|for|showing)\b",
    r"\bchart\b",
    r"\bgraph\b",
    r"\bvisuali[sz]e\b",
    r"\bvisuali[sz]ation\b",
    r"\bshow\b[^.?!]{0,48}\b(?:chart|graph|plot|visual)\b",
    r"\bdisplay\b[^.?!]{0,48}\b(?:chart|graph|plot|visual)\b",
    r"\bas a (?:chart|graph|plot)\b",
    r"\btrend\b[^.?!]{0,32}\b(?:chart|graph|plot|visual)\b",
    r"\b(?:chart|graph|plot|visual)\b[^.?!]{0,32}\btrend\b",
)

_AFFIRMATIVE_CHART_REPLIES = (
    r"^yes(?:\s+please)?[!.]*$",
    r"^yeah[!.]*$",
    r"^yep[!.]*$",
    r"^sure[!.]*$",
    r"^(?:ok|okay)(?:\s+please)?[!.]*$",
    r"^please[!.]*$",
    r"^go ahead[!.]*$",
    r"^do it[!.]*$",
    r"^show (?:it|me|the chart)(?:\s+please)?[!.]*$",
    r"^visuali[sz]e (?:it|this)(?:\s+please)?[!.]*$",
    r"^show (?:a |the )?(?:chart|graph)[!.]*$",
)

_CHART_ANSWER_PATTERNS = (
    r"\bhere(?:'s| is) (?:the |a )?(?:(?:line|bar|pie|column|area|scatter)\s+)?(?:chart|graph)\b",
    r"\bhere(?:'s| is) (?:the |a )?(?:line|bar|pie|column|area)\s+(?:chart|graph|plot)\b",
    r"\bhere(?:'s| is) (?:the |a )?line chart representing\b",
    r"\b(?:line|bar|pie|column|area)\s+(?:chart|graph|plot) (?:depicting|showing|of|for|representing)\b",
    r"\bvisualized as (?:a |the )?(?:pie|bar|line|column|area)?\s*(?:chart|graph)\b",
    r"\bview (?:the |a )?(?:pie|bar|line|column|area)?\s*(?:chart|graph)\b",
    r"\b(?:pie|bar|line) chart (?:provides|helps|shows)\b",
    r"\bincluded in the chart\b",
    r"\b(?:the |this |following )?(?:chart|graph) (?:below|above|shows|illustrates|displays|represents|depicts|highlights)\b",
    r"\b(?:chart|graph) below\b",
    r"\bsee (?:the )?(?:chart|graph)\b",
    r"\b(?:shown|presented|illustrated|depicted) (?:in|as) (?:the |a |this )?(?:chart|graph)\b",
    r"\bi(?:'ve| have) (?:created|generated|built|plotted) (?:a |the )?(?:chart|graph|visualization|visualisation)\b",
    r"\bcreated (?:a |the )?(?:chart|graph|visualization|visualisation)\b",
    r"\b(?:chart|graph) (?:is|has been) (?:shown|displayed|included|rendered|plotted)\b",
    r"\b(?:view|interact with) (?:this |the )?chart\b",
    r"\bx-axis\b.*\by-axis\b",
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class FabricDataAgentClient:
    """
    Client for calling Microsoft Fabric Data Agents from external applications.
    
    This client handles:
    - Interactive browser authentication with Azure AD
    - Automatic token refresh
    - Bearer token management for API calls
    - Proper cleanup of resources
    """
    
    def __init__(self, tenant_id: str, data_agent_url: str):
        """
        Initialize the Fabric Data Agent client.
        
        Args:
            tenant_id (str): Your Azure tenant ID
            data_agent_url (str): The published URL of your Fabric Data Agent
        """
        self.tenant_id = tenant_id
        self.data_agent_url = data_agent_url
        self.token = None
        self.token_expires_on = 0
        
        # Validate inputs
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not data_agent_url:
            raise ValueError("data_agent_url is required")
        
        print(f"Initializing Fabric Data Agent Client...")
        print(f"Tenant ID: {tenant_id}")
        print(f"Data Agent URL: {data_agent_url}")
    
    def _authenticate(self):
        """
        Ensure a valid token is available (uses shared Microsoft login session).
        """
        self._refresh_token()
    
    def _refresh_token(self):
        """
        Refresh the authentication token.
        """
        try:
            logger.info("Refreshing authentication token...")
            self.token = acquire_fabric_token()
            self.token_expires_on = self.token.expires_on

        except Exception as e:
            logger.error("Token refresh failed: %s", e)
            raise

    def _ensure_fresh_token(self):
        session_token = acquire_fabric_token()
        if (
            not self.token
            or self.token.token != session_token.token
            or self.token_expires_on <= (time.time() + 60)
        ):
            self.token = session_token
            self.token_expires_on = session_token.expires_on
    
    def _get_openai_client(self, request_timeout: float = DEFAULT_TIMEOUT) -> OpenAI:
        """
        Create an OpenAI client configured for Fabric Data Agent calls.
        
        Returns:
            OpenAI: Configured OpenAI client
        """
        self._ensure_fresh_token()

        if not self.token:
            raise ValueError("No valid authentication token available")
        
        # Fabric auth uses Azure AD bearer tokens in the Authorization header,
        # not an OpenAI API key. The SDK still requires a non-empty api_key.
        # Short per-request timeout; polling handles long-running agent runs.
        return OpenAI(
            api_key="not-used",
            base_url=self.data_agent_url,
            timeout=HTTP_REQUEST_TIMEOUT,
            max_retries=3,
            default_query={"api-version": "2024-05-01-preview"},
            default_headers={
                "Authorization": f"Bearer {self.token.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "ActivityId": str(uuid.uuid4())
            }
        )

    @staticmethod
    def is_fabric_access_error(message: str) -> bool:
        lowered = str(message or "").lower()
        return (
            "itemnotfound" in lowered
            or "error code: 404" in lowered
            or "error code: 403" in lowered
            or "insufficientprivileges" in lowered
            or "user id" in lowered and "don't match" in lowered
            or "could not found the requested item" in lowered
            or "does not have access to the fabric data agent" in lowered
            or "couldn't reach the fabric data agent" in lowered
        )

    @staticmethod
    def format_fabric_error(error: Exception | str, user_email: Optional[str] = None) -> str:
        message = str(error).strip()
        lowered = message.lower()
        if "user id" in lowered and "don't match" in lowered:
            return (
                "Your Microsoft sign-in no longer matches this chat session. "
                "Click New chat, or sign out and sign in again, then retry your question."
            )
        if FabricDataAgentClient.is_fabric_access_error(message):
            return (
                "I couldn't reach the Fabric Data Agent. The workspace or agent URL may be wrong, "
                "or your account may not have access. Ask your administrator to verify backend/agents.json."
            )
        cleaned = message.removeprefix("Error:").strip()
        return cleaned or "Something went wrong while contacting the data agent."

    def _format_fabric_error(self, error: Exception, user_email: Optional[str] = None) -> str:
        return self.format_fabric_error(error, user_email)

    def _create_thread_via_openai(self, client: OpenAI, thread_name: str) -> dict:
        thread = client.beta.threads.create(timeout=HTTP_REQUEST_TIMEOUT)
        return {"id": thread.id, "name": thread_name}

    def _get_existing_or_create_new_thread(self, data_agent_url: str, thread_name = None) -> dict:
        """
        Get an existing thread or Create a new thread for the target Fabric Data Agent.

        Args:
            data_agent_url (str): The URL of the Fabric Data Agent
            thread_name (str, optional): Name for the new or existing thread. If None, a random name is generated.

        Returns:
            list: A list containing the ID and name of the created thread or existing thread
        """
        if thread_name == None: # if None, generate a random thread name to create a new thread
            thread_name = f'external-client-thread-{uuid.uuid4()}'
        else:
            thread_name = thread_name # use provided thread name to attempt to get existing thread, if not create new thread

        self._ensure_fresh_token()
        
        if "aiskills" in data_agent_url: # future proofing for different url formats
            base_url = data_agent_url.replace("aiskills", "dataagents").removesuffix("/openai").replace("/aiassistant","/__private/aiassistant")
        else:
            base_url = data_agent_url.removesuffix("/openai").replace("/aiassistant","/__private/aiassistant")
        
        get_new_thread_url = f'{base_url}/threads/fabric?tag="{thread_name}"'

        headers = {
            "Authorization": f"Bearer {self.token.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ActivityId": str(uuid.uuid4())
        }

        response = requests.get(get_new_thread_url, headers=headers, timeout=HTTP_REQUEST_TIMEOUT)
        if response.status_code == 404:
            client = self._get_openai_client()
            return self._create_thread_via_openai(client, thread_name)

        if response.status_code == 403 and "user id" in response.text.lower():
            client = self._get_openai_client()
            return self._create_thread_via_openai(client, thread_name)

        response.raise_for_status()
        thread = response.json()
        thread["name"] = thread_name #adding thread name to returned object

        return thread

    def _monitor_run(self, client: OpenAI, thread_id: str, run, timeout: int):
        """Poll run status until completion or timeout."""
        start_time = time.time()
        while run.status in ["queued", "in_progress"]:
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Data agent did not finish within {timeout} seconds. "
                    "Try a simpler question or increase the timeout."
                )

            print(f"⏳ Status: {run.status}")
            time.sleep(POLL_INTERVAL_SECONDS)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id,
                timeout=HTTP_REQUEST_TIMEOUT,
            )
        return run

    def _extract_message_text(self, msg) -> Optional[str]:
        try:
            content = msg.content[0]
            if hasattr(content, 'text'):
                text_content = getattr(content, 'text', None)
                if text_content is not None and hasattr(text_content, 'value'):
                    return text_content.value
                if text_content is not None:
                    return str(text_content)
                return str(content)
            return str(content)
        except (IndexError, AttributeError):
            return str(msg.content)

    def _extract_assistant_responses(self, messages, run_id: Optional[str] = None) -> list[str]:
        """Return assistant text for the current run only (not full thread history)."""
        if run_id is not None:
            matched = []
            for msg in messages.data:
                if msg.role != "assistant":
                    continue
                if getattr(msg, 'run_id', None) == run_id:
                    text = self._extract_message_text(msg)
                    if text:
                        matched.append(text)
            if matched:
                return matched

        # Fallback: newest assistant message only (messages.list uses order=desc)
        for msg in messages.data:
            if msg.role == "assistant":
                text = self._extract_message_text(msg)
                if text:
                    return [text]

        return []

    def _maybe_cleanup_thread(self, client: OpenAI, thread: dict, preserve_thread: bool):
        if preserve_thread:
            return
        try:
            client.beta.threads.delete(thread_id=thread['id'])
        except Exception as cleanup_error:
            print(f"⚠️ Cleanup warning: {cleanup_error}")

    def _extract_reframed_query(self, steps, original_question: str) -> Optional[str]:
        """Extract the reframed query the data agent used internally."""
        import json

        original = original_question.strip().lower()
        candidates = []
        question_keys = {
            'question', 'query', 'user_query', 'user_question', 'reframed_query',
            'rewritten_query', 'enhanced_query', 'natural_language_query', 'intent',
            'search_query', 'nl_query', 'prompt', 'input', 'task', 'instruction',
        }

        def collect_from_value(value, depth=0):
            if depth > 6:
                return
            if isinstance(value, str):
                text = value.strip()
                if len(text) > 8 and text.lower() != original:
                    candidates.append(text)
            elif isinstance(value, dict):
                for key, nested in value.items():
                    if key.lower() in question_keys and isinstance(nested, str) and nested.strip():
                        candidates.append(nested.strip())
                    collect_from_value(nested, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    collect_from_value(item, depth + 1)

        try:
            for step in steps.data:
                if not hasattr(step, 'step_details') or not step.step_details:
                    continue
                details = step.step_details
                payload = details.model_dump() if hasattr(details, 'model_dump') else details
                collect_from_value(payload)
        except Exception as e:
            print(f"⚠️ Warning: Could not extract reframed query: {e}")

        for candidate in candidates:
            normalized = candidate.strip().lower()
            if normalized != original and len(candidate) >= max(12, len(original_question) * 0.4):
                return candidate.strip()

        return candidates[0].strip() if candidates else None

    @staticmethod
    def _is_vega_lite_spec(value) -> bool:
        if not isinstance(value, dict):
            return False
        schema = str(value.get("$schema", "")).lower()
        if "vega-lite" in schema:
            return True
        return "mark" in value and "encoding" in value

    @staticmethod
    def _is_pbir_visual_spec(value) -> bool:
        if not isinstance(value, dict):
            return False
        visual = value.get("visual")
        if not isinstance(visual, dict):
            visual = value.get("payload", {}).get("visual") if isinstance(value.get("payload"), dict) else None
        return isinstance(visual, dict) and bool(visual.get("visualType"))

    @staticmethod
    def _parse_markdown_table_to_rows(lines) -> list[dict]:
        import re

        if isinstance(lines, str):
            lines = lines.splitlines()

        table_lines = []
        for line in lines:
            stripped = str(line).strip()
            if "|" not in stripped:
                continue
            if re.match(r"^[\|\s\-:]+$", stripped):
                continue
            table_lines.append(stripped)

        if len(table_lines) < 2:
            return []

        def split_row(line: str) -> list[str]:
            return [cell.strip() for cell in line.strip().strip("|").split("|")]

        headers = split_row(table_lines[0])
        if not headers:
            return []

        rows = []
        for line in table_lines[1:]:
            cells = split_row(line)
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            row = {headers[index]: cells[index] if index < len(cells) else "" for index in range(len(headers))}
            if any(str(value).strip() for value in row.values()):
                rows.append(row)
        return rows

    def _normalize_row_values(self, rows: list[dict]) -> list[dict]:
        normalized = []
        for row in rows:
            next_row = {}
            for key, value in row.items():
                flat_key = self._resolve_field_name(key) or str(key)
                if value is None or value == "":
                    next_row[flat_key] = value
                    continue
                if isinstance(value, dict):
                    inner_value = value.get("value")
                    if inner_value is not None:
                        next_row[flat_key] = inner_value
                        continue
                    if value.get("type") and value.get("name"):
                        continue
                if isinstance(value, (int, float)):
                    next_row[flat_key] = value
                    continue
                text = str(value).strip().replace(",", "")
                try:
                    if "." in text:
                        next_row[flat_key] = float(text)
                    else:
                        next_row[flat_key] = int(text)
                except ValueError:
                    next_row[flat_key] = value
            normalized.append(next_row)
        return normalized

    @staticmethod
    def _resolve_field_name(field) -> Optional[str]:
        import ast
        import re

        if field is None:
            return None
        if isinstance(field, dict):
            for key in ("field", "name", "Property"):
                nested = field.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
                if isinstance(nested, dict):
                    resolved = FabricDataAgentClient._resolve_field_name(nested)
                    if resolved:
                        return resolved
            return None

        text = str(field).strip()
        if not text:
            return None

        for pattern in (
            r"['\"]name['\"]\s*:\s*['\"]([^'\"]+)['\"]",
            r"['\"]Property['\"]\s*:\s*['\"]([^'\"]+)['\"]",
            r"['\"]field['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = ast.literal_eval(text)
                return FabricDataAgentClient._resolve_field_name(parsed)
            except (SyntaxError, ValueError):
                pass

        return text

    @staticmethod
    def _humanize_field_name(name: str) -> str:
        import re
        return re.sub(r"\s+", " ", str(name).replace("_", " ")).strip()

    def _sanitize_text_label(self, value) -> Optional[str]:
        resolved = self._resolve_field_name(value)
        if resolved:
            return self._humanize_field_name(resolved)
        if isinstance(value, dict) and value.get("text"):
            return self._sanitize_text_label(value["text"])
        if isinstance(value, str):
            text = value.strip()
            if not text or text.startswith("{"):
                return None
            if len(text) > 80:
                return None
            return text
        return None

    def _sanitize_encoding_channel(self, channel):
        if isinstance(channel, list):
            return [self._sanitize_encoding_channel(item) for item in channel]
        if not isinstance(channel, dict):
            return channel

        sanitized = dict(channel)
        resolved_field = self._resolve_field_name(sanitized.get("field"))
        if resolved_field:
            sanitized["field"] = resolved_field
        elif "field" in sanitized:
            sanitized.pop("field", None)

        clean_title = self._sanitize_text_label(sanitized.get("title"))
        if clean_title:
            sanitized["title"] = clean_title
        else:
            sanitized.pop("title", None)

        for nested_key in ("axis", "legend"):
            nested = sanitized.get(nested_key)
            if isinstance(nested, dict):
                nested = dict(nested)
                nested_title = self._sanitize_text_label(nested.get("title"))
                if nested_title:
                    nested["title"] = nested_title
                else:
                    nested.pop("title", None)
                sanitized[nested_key] = nested

        return sanitized

    def _align_field_to_columns(self, field_name: Optional[str], columns: list[str]) -> Optional[str]:
        if not field_name:
            return field_name
        if field_name in columns:
            return field_name

        lowered = field_name.lower()
        for column in columns:
            if column.lower() == lowered:
                return column
            if column.replace("_", "").lower() == field_name.replace("_", "").lower():
                return column
        return field_name

    def _sanitize_vega_spec(self, spec: dict) -> dict:
        merged = json.loads(json.dumps(spec, default=str))
        merged["$schema"] = VEGA_LITE_SCHEMA

        data_values = merged.get("data", {}).get("values") if isinstance(merged.get("data"), dict) else None
        if isinstance(data_values, list):
            merged["data"]["values"] = self._normalize_row_values(
                [row for row in data_values if isinstance(row, dict)]
            )
            columns = list(merged["data"]["values"][0].keys()) if merged["data"]["values"] else []
        else:
            columns = []

        encoding = merged.get("encoding")
        if isinstance(encoding, dict):
            sanitized_encoding = {}
            for channel_name, channel_value in encoding.items():
                sanitized_channel = self._sanitize_encoding_channel(channel_value)
                if isinstance(sanitized_channel, dict) and columns and sanitized_channel.get("field"):
                    sanitized_channel["field"] = self._align_field_to_columns(
                        sanitized_channel["field"],
                        columns,
                    )
                sanitized_encoding[channel_name] = sanitized_channel
            merged["encoding"] = sanitized_encoding

        title = merged.get("title")
        title_text = title.get("text") if isinstance(title, dict) else title
        if isinstance(title_text, str):
            lowered = title_text.lower()
            if lowered.startswith("here is a") or lowered.startswith("here is the") or len(title_text) > 80:
                merged.pop("title", None)

        merged["autosize"] = {"type": "pad", "contains": "padding", "resize": False}
        if merged.get("width") == "container" or not merged.get("width"):
            merged["width"] = 400
        if not merged.get("height"):
            merged["height"] = 300

        return merged

    def _extract_row_tables_from_text(self, text: str) -> list[list[dict]]:
        import re

        tables: list[list[dict]] = []
        if not text:
            return tables

        markdown_table = self._extract_markdown_table(text)
        if markdown_table:
            rows = self._parse_markdown_table_to_rows(markdown_table.splitlines())
            if rows:
                tables.append(self._normalize_row_values(rows))

        for match in re.finditer(r"\[\s*\{", text):
            snippet = text[match.start():]
            for end in range(len(snippet), 2, -1):
                try:
                    parsed = json.loads(snippet[:end])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    tables.append(self._normalize_row_values(parsed))
                    break

        tables.extend(self._parse_list_tables_from_text(text))
        tables.extend(self._parse_trend_rows_from_text(text))

        return tables

    def _extract_row_tables_from_previews(self, previews) -> list[list[dict]]:
        tables: list[list[dict]] = []
        for preview in previews or []:
            if isinstance(preview, list):
                rows = self._parse_markdown_table_to_rows(preview)
                if rows:
                    tables.append(self._normalize_row_values(rows))
            elif isinstance(preview, str) and "|" in preview:
                rows = self._parse_markdown_table_to_rows(preview.splitlines())
                if rows:
                    tables.append(self._normalize_row_values(rows))
        return tables

    def _extract_all_row_tables(
        self,
        steps,
        sql_previews,
        messages,
        answer: str,
        question: str = "",
    ) -> list[list[dict]]:
        tables: list[list[dict]] = []
        tables.extend(self._extract_raw_tables_from_steps(steps))
        tables.extend(self._extract_row_tables_from_previews(sql_previews))
        tables.extend(self._extract_row_tables_from_text(answer))
        tables.extend(self._extract_row_tables_from_text(question))

        if messages:
            try:
                for msg in messages.data:
                    text = self._extract_message_text(msg)
                    if text:
                        tables.extend(self._extract_row_tables_from_text(text))
            except Exception as exc:
                print(f"⚠️ Warning: Could not parse conversation tables: {exc}")

        unique_tables: list[list[dict]] = []
        seen = set()
        for table in tables:
            if not table or not isinstance(table[0], dict):
                continue
            normalized = self._normalize_row_values(table)
            signature = (tuple(sorted(normalized[0].keys())), len(normalized), json.dumps(normalized[:3], sort_keys=True, default=str))
            if signature in seen:
                continue
            seen.add(signature)
            unique_tables.append(normalized)
        return unique_tables

    @staticmethod
    def _pbir_visual_type_to_mark(visual_type: str) -> str:
        lowered = (visual_type or "").lower()
        if "pie" in lowered or "donut" in lowered:
            return "arc"
        if "line" in lowered:
            return "line"
        if "area" in lowered:
            return "area"
        if "scatter" in lowered:
            return "point"
        if "bar" in lowered or "column" in lowered:
            return "bar"
        return "bar"

    def _pbir_field_from_projection(self, projection: dict) -> Optional[str]:
        field = projection.get("field", {}) if isinstance(projection, dict) else {}
        for key in ("Column", "Measure", "Aggregation"):
            node = field.get(key)
            if isinstance(node, dict) and node.get("Property"):
                return str(node["Property"])
        return None

    def _pbir_to_vega_spec(self, pbir_spec: dict, rows: list[dict]) -> Optional[dict]:
        visual = pbir_spec.get("visual")
        if not isinstance(visual, dict):
            payload = pbir_spec.get("payload")
            visual = payload.get("visual") if isinstance(payload, dict) else None
        if not isinstance(visual, dict):
            return None

        visual_type = str(visual.get("visualType") or "")
        mark_type = self._pbir_visual_type_to_mark(visual_type)
        query_state = visual.get("query", {}).get("queryState", {})
        if not isinstance(query_state, dict):
            query_state = {}

        fields = {}
        for bucket, config in query_state.items():
            if not isinstance(config, dict):
                continue
            for projection in config.get("projections", []) or []:
                field_name = self._pbir_field_from_projection(projection)
                if field_name:
                    fields[str(bucket).lower()] = field_name

        columns = list(rows[0].keys()) if rows else []
        numeric_cols = [col for col in columns if self._column_is_numeric(rows, col)] if rows else []
        category_cols = [col for col in columns if col not in numeric_cols] if rows else []

        value_field = fields.get("y") or fields.get("values") or fields.get("value") or (numeric_cols[0] if numeric_cols else None)
        category_field = (
            fields.get("category")
            or fields.get("series")
            or fields.get("legend")
            or (category_cols[0] if category_cols else None)
        )

        if not value_field:
            return None

        if mark_type == "arc":
            encoding = {
                "theta": {"field": value_field, "type": "quantitative", "aggregate": "sum"},
                "color": {"field": category_field or category_cols[0] if category_cols else columns[0], "type": "nominal"},
            }
        else:
            x_field = fields.get("category") or fields.get("x") or category_field or (columns[0] if columns else None)
            encoding = {
                "x": {"field": x_field, "type": "nominal"},
                "y": {"field": value_field, "type": "quantitative", "aggregate": "sum"},
            }
            series_field = fields.get("series") or fields.get("legend")
            if series_field:
                encoding["color"] = {"field": series_field, "type": "nominal"}

        return {
            "$schema": VEGA_LITE_SCHEMA,
            "width": 400,
            "height": 300,
            "data": {"values": rows},
            "mark": {"type": mark_type, "point": mark_type == "line"},
            "encoding": encoding,
        }

    @staticmethod
    def _question_requests_chart(question: str) -> bool:
        text = (question or "").strip().lower()
        if not text:
            return False

        sanitized = re.sub(r"\bbarcodes?\b", "", text)
        for pattern in _CHART_QUESTION_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                return True

        if re.search(r"\bbar\b", sanitized) and re.search(
            r"\b(?:chart|graph|plot|compare|comparison|visual)\b", sanitized
        ):
            return True

        return False

    @staticmethod
    def _is_affirmative_chart_followup(question: str) -> bool:
        text = re.sub(r"\s+", " ", (question or "").strip().lower())
        if not text:
            return False
        return any(re.match(pattern, text, re.IGNORECASE) for pattern in _AFFIRMATIVE_CHART_REPLIES)

    @classmethod
    def _should_show_charts(cls, question: str, answer: str) -> bool:
        if cls._question_requests_chart(question):
            return True
        return cls._is_affirmative_chart_followup(question) and cls._answer_describes_chart(answer)

    @staticmethod
    def _answer_describes_chart(answer: str) -> bool:
        text = (answer or "").lower()
        if not text:
            return False
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in _CHART_ANSWER_PATTERNS)

    @staticmethod
    def _requested_chart_mark(question: str, answer: str, temporal_col: Optional[str]) -> str:
        combined = f"{(question or '').lower()} {(answer or '').lower()}"
        if re.search(r"\bpie\s*(?:chart|graph|plot)?\b", combined) or re.search(
            r"\b(?:donut|doughnut)\s+(?:chart|graph|plot)\b", combined
        ):
            return "arc"
        if re.search(r"\b(?:bar|column)\s+(?:chart|graph|plot)\b", combined):
            return "bar"
        if re.search(r"\bline\s+(?:chart|graph|plot)\b", combined):
            return "line"
        if re.search(r"\btrends?\s+over\s+time\b", combined) or re.search(r"\bsales\s+trends?\b", combined):
            return "line"
        if temporal_col and re.search(r"\btrend\b", combined):
            return "line"
        if temporal_col:
            return "line"
        return "bar"

    @staticmethod
    def _parse_top_n_from_text(text: str) -> Optional[int]:
        if not text:
            return None
        match = re.search(r"\btop\s+(\d{1,2})\b", text, re.IGNORECASE)
        if not match:
            return None
        return max(1, min(int(match.group(1)), 25))

    @staticmethod
    def _extract_answer_list_names(text: str) -> list[str]:
        if not text:
            return []

        names: list[str] = []
        list_started = False
        stop_markers = (
            "next step",
            "suggested question",
            "would you like",
            "want to compare",
            "interested in",
            "can you display",
            "you may want",
        )

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if names:
                    list_started = True
                continue

            lowered = line.lower()
            if any(marker in lowered for marker in stop_markers):
                break

            if re.search(r"\binclude:\s*$|\bare:\s*$|\bstores include\b|\bin the chart are:\s*$", line, re.IGNORECASE):
                list_started = True
                continue

            cleaned = re.sub(r"^(?:[-*•]|\d+\.)\s*", "", line)
            if re.match(r"^(?P<name>.+?)\s*[:|-]\s*(?P<value>[\d,]+(?:\.\d+)?)\s*$", cleaned):
                match = re.match(r"^(?P<name>.+?)\s*[:|-]\s*(?P<value>[\d,]+(?:\.\d+)?)\s*$", cleaned)
                names.append(match.group("name").strip())
                list_started = True
                continue

            looks_like_store = (
                list_started
                or "ltd" in lowered
                or lowered.startswith("pt-")
                or "shoppers stop" in lowered
                or "fresco" in lowered
            )
            if looks_like_store and 4 <= len(cleaned) <= 120 and not cleaned.endswith("?"):
                if not re.match(r"^(the|this|you|it|that)\b", lowered):
                    names.append(cleaned)
                    list_started = True

        return names

    @classmethod
    def _should_infer_chart(cls, question: str, answer: str) -> bool:
        return cls._should_show_charts(question, answer)

    def _parse_trend_rows_from_text(self, text: str) -> list[list[dict]]:
        if not text:
            return []

        trend_line = re.compile(
            r"^(?P<period>(?:[A-Za-z]{3}-\d{4})|(?:\d{4}-\d{2}(?:-\d{2})?))"
            r"\s*:\s*"
            r"(?P<qty>[\d,]+)\s*qty"
            r"(?:,\s*[₹$€]?\s*(?P<amount>[\d,]+(?:\.\d+)?))?",
            re.IGNORECASE,
        )
        rows: list[dict] = []
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("-•* ").strip()
            if not line:
                continue
            match = trend_line.match(line)
            if not match:
                continue
            row = {
                "period": match.group("period"),
                "quantity": int(match.group("qty").replace(",", "")),
            }
            amount = match.group("amount")
            if amount:
                row["sales_amount"] = float(amount.replace(",", ""))
            rows.append(row)

        return [self._normalize_row_values(rows)] if len(rows) >= 2 else []

    def _parse_list_tables_from_text(self, text: str) -> list[list[dict]]:
        rows: list[dict] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^(?:[-*•]|\d+\.)\s*", "", line)
            match = re.match(r"^(?P<name>.+?)\s*[:|-]\s*(?P<value>-?[\d,]+(?:\.\d+)?)\s*$", cleaned)
            if not match:
                continue
            rows.append(
                {
                    "name": match.group("name").strip(),
                    "value": float(match.group("value").replace(",", "")),
                }
            )

        return [self._normalize_row_values(rows)] if len(rows) >= 2 else []

    def _find_value_column(self, columns: list[str], rows: list[dict]) -> Optional[str]:
        numeric_cols = [col for col in columns if self._column_is_mostly_numeric(rows, col)]
        if not numeric_cols:
            return None
        return next(
            (
                col
                for col in numeric_cols
                if any(token in col.lower() for token in ("qty", "quantity", "sales", "volume", "sold", "amount", "total", "value", "count"))
            ),
            numeric_cols[0],
        )

    def _find_category_column(self, columns: list[str], rows: list[dict], value_col: Optional[str]) -> Optional[str]:
        category_cols = [col for col in columns if col != value_col and not self._column_is_mostly_numeric(rows, col)]
        if not category_cols:
            category_cols = [col for col in columns if col != value_col]
        if not category_cols:
            return None
        return next(
            (
                col
                for col in category_cols
                if any(token in col.lower() for token in ("store", "site", "name", "customer", "product", "sku", "region"))
            ),
            category_cols[0],
        )

    @staticmethod
    def _column_is_mostly_numeric(rows: list[dict], column: str) -> bool:
        checked = 0
        numeric = 0
        for row in rows[:50]:
            value = row.get(column)
            if value is None or value == "":
                continue
            checked += 1
            if isinstance(value, (int, float)):
                numeric += 1
                continue
            try:
                float(str(value).replace(",", ""))
                numeric += 1
            except ValueError:
                pass
        return checked > 0 and numeric / checked >= 0.8

    def _filter_rows_by_names(self, rows: list[dict], category_col: str, names: list[str]) -> list[dict]:
        if not rows or not names or not category_col:
            return rows

        filtered: list[dict] = []
        lowered_names = [name.lower() for name in names]
        for row in rows:
            value = str(row.get(category_col, "")).strip().lower()
            if not value:
                continue
            if any(name in value or value in name for name in lowered_names):
                filtered.append(row)

        return filtered

    def _prepare_chart_rows(self, tables: list[list[dict]], question: str, answer: str) -> Optional[list[dict]]:
        if not tables:
            return None

        best = max(tables, key=len)
        if not best:
            return None

        columns = list(best[0].keys())
        value_col = self._find_value_column(columns, best)
        category_col = self._find_category_column(columns, best, value_col)
        answer_names = self._extract_answer_list_names(answer)
        top_n = self._parse_top_n_from_text(f"{question} {answer}")

        rows = list(best)
        if answer_names and category_col:
            matched = self._filter_rows_by_names(rows, category_col, answer_names)
            if matched:
                rows = matched
            elif value_col:
                # Preserve answer order when names are listed without numeric values in the reply.
                ordered = []
                for name in answer_names:
                    for row in rows:
                        value = str(row.get(category_col, "")).strip().lower()
                        if name.lower() in value or value in name.lower():
                            ordered.append(row)
                            break
                if ordered:
                    rows = ordered

        has_temporal = any(self._looks_like_temporal_column(col) for col in columns)
        category_values = [str(row.get(category_col, "")).strip() for row in rows if category_col]
        rows_are_monthly = bool(category_values) and all(
            self._is_month_label(value) for value in category_values
        )
        if value_col and not has_temporal and not rows_are_monthly:
            rows = sorted(
                rows,
                key=lambda row: float(str(row.get(value_col, 0)).replace(",", "") or 0),
                reverse=True,
            )

        if top_n:
            rows = rows[:top_n]
        elif self._requested_chart_mark(question, answer, None) == "arc":
            rows = rows[:10]

        return rows if rows else None

    def _collect_chart_payloads(self, value, specs: list, tables: list, depth: int = 0) -> None:
        if depth > 14:
            return

        if isinstance(value, dict):
            for key in (
                "vegaLiteSpec",
                "vega_lite_spec",
                "report_spec",
                "visual_spec",
                "chart_spec",
                "spec",
            ):
                nested = value.get(key)
                if self._is_vega_lite_spec(nested):
                    specs.append(nested)

            if "report_specs" in value:
                report_specs = value["report_specs"]
                if isinstance(report_specs, list):
                    for item in report_specs:
                        if self._is_vega_lite_spec(item):
                            specs.append(item)
                        elif isinstance(item, dict) and self._is_vega_lite_spec(item.get("spec")):
                            specs.append(item["spec"])
                        elif isinstance(item, dict) and self._is_pbir_visual_spec(item):
                            specs.append(item)

            for key, nested in value.items():
                key_lower = str(key).lower()
                if "report_spec" in key_lower and isinstance(nested, (dict, list, str)):
                    self._collect_chart_payloads(nested, specs, tables, depth + 1)

            if self._is_pbir_visual_spec(value):
                specs.append(value)

            for key in ("data", "rows", "results", "records", "values", "items", "preview", "table", "dataset"):
                nested = value.get(key)
                if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                    tables.append(nested)

            columns = value.get("columns")
            row_values = value.get("rows")
            if isinstance(columns, list) and isinstance(row_values, list) and columns and row_values:
                materialized = []
                for row in row_values:
                    if isinstance(row, dict):
                        materialized.append(row)
                    elif isinstance(row, list):
                        materialized.append(
                            {
                                str(columns[index]): row[index]
                                for index in range(min(len(columns), len(row)))
                            }
                        )
                if materialized:
                    tables.append(materialized)

            for nested in value.values():
                self._collect_chart_payloads(nested, specs, tables, depth + 1)
            return

        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                if self._is_vega_lite_spec(value[0]):
                    specs.extend(item for item in value if self._is_vega_lite_spec(item))
                elif len(value) >= 2:
                    tables.append(value)
            elif value and isinstance(value[0], list):
                header = value[0]
                if header and all(isinstance(item, str) for item in header):
                    materialized = []
                    for row in value[1:]:
                        if isinstance(row, list):
                            materialized.append(
                                {
                                    header[index]: row[index]
                                    for index in range(min(len(header), len(row)))
                                }
                            )
                    if materialized:
                        tables.append(materialized)
            for item in value:
                self._collect_chart_payloads(item, specs, tables, depth + 1)
            return

        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return
            self._collect_chart_payloads(parsed, specs, tables, depth + 1)

    def _iter_step_payloads(self, steps):
        if not steps:
            return

        for step in steps.data:
            details = getattr(step, "step_details", None)
            if not details:
                continue

            yield details.model_dump() if hasattr(details, "model_dump") else details

            tool_calls = getattr(details, "tool_calls", None) or []
            for tool_call in tool_calls:
                for attr in ("output", "function"):
                    value = getattr(tool_call, attr, None)
                    if value is not None:
                        yield value
                if hasattr(tool_call, "model_dump"):
                    yield tool_call.model_dump()

    def _extract_raw_tables_from_steps(self, steps) -> list[list[dict]]:
        tables: list[list[dict]] = []
        if not steps:
            return tables

        try:
            for payload in self._iter_step_payloads(steps):
                scratch_specs: list = []
                scratch_tables: list = []
                self._collect_chart_payloads(payload, scratch_specs, scratch_tables)
                for table in scratch_tables:
                    if table and isinstance(table[0], dict):
                        tables.append(table)
        except Exception as exc:
            print(f"⚠️ Warning: Could not extract chart tables: {exc}")

        unique_tables: list[list[dict]] = []
        seen = set()
        for table in tables:
            signature = tuple(sorted(table[0].keys()))
            if signature in seen:
                continue
            seen.add(signature)
            unique_tables.append(table)
        return unique_tables

    def _extract_vega_specs_from_steps(self, steps) -> list[dict]:
        specs: list[dict] = []
        if not steps:
            return specs

        try:
            for payload in self._iter_step_payloads(steps):
                scratch_tables: list = []
                self._collect_chart_payloads(payload, specs, scratch_tables)
        except Exception as exc:
            print(f"⚠️ Warning: Could not extract Vega-Lite specs: {exc}")

        unique_specs: list[dict] = []
        seen = set()
        for spec in specs:
            signature = json.dumps(spec, sort_keys=True, default=str)
            if signature in seen:
                continue
            seen.add(signature)
            unique_specs.append(spec)
        return unique_specs

    def _extract_chart_images_from_messages(self, messages, run_id: Optional[str] = None) -> list[dict]:
        images: list[dict] = []
        if not messages:
            return images

        try:
            for msg in messages.data:
                if msg.role != "assistant":
                    continue
                if run_id is not None and getattr(msg, "run_id", None) != run_id:
                    continue

                for block in getattr(msg, "content", []) or []:
                    block_type = getattr(block, "type", None)
                    if block_type == "image_url":
                        image_url = getattr(getattr(block, "image_url", None), "url", None)
                        if image_url:
                            images.append({"image_url": image_url})
                    elif block_type == "image_file":
                        file_id = getattr(getattr(block, "image_file", None), "file_id", None)
                        if file_id:
                            images.append({"image_url": f"openai-file://{file_id}"})
        except Exception as exc:
            print(f"⚠️ Warning: Could not extract chart images: {exc}")

        return images

    @staticmethod
    def _looks_like_temporal_column(name: str) -> bool:
        lowered = name.lower()
        return any(
            token in lowered
            for token in ("date", "time", "day", "month", "year", "week", "period", "timestamp")
        )

    @staticmethod
    def _is_month_label(value: str) -> bool:
        lowered = (value or "").strip().lower()
        if not lowered:
            return False
        month_names = (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
        )
        return lowered in month_names or any(lowered.startswith(name) for name in month_names)

    @staticmethod
    def _column_is_numeric(rows: list[dict], column: str) -> bool:
        checked = 0
        numeric = 0
        for row in rows[:20]:
            value = row.get(column)
            if value is None or value == "":
                continue
            checked += 1
            if isinstance(value, (int, float)):
                numeric += 1
                continue
            try:
                float(str(value).replace(",", ""))
                numeric += 1
            except ValueError:
                return False
        return checked > 0 and numeric == checked

    def _infer_chart_spec(self, question: str, answer: str, rows: list[dict]) -> Optional[dict]:
        if not rows or not isinstance(rows[0], dict):
            return None

        if not self._should_infer_chart(question, answer):
            return None

        rows = self._normalize_row_values(rows)
        columns = list(rows[0].keys())
        if not columns:
            return None

        temporal_cols = [col for col in columns if self._looks_like_temporal_column(col)]
        numeric_cols = [col for col in columns if self._column_is_mostly_numeric(rows, col)]
        category_cols = [col for col in columns if col not in numeric_cols]
        series_cols = [col for col in category_cols if col not in temporal_cols]

        if not numeric_cols:
            return None

        value_col = next(
            (col for col in numeric_cols if any(token in col.lower() for token in ("stock", "qty", "quantity", "total", "amount", "value", "count", "sales", "volume", "sold"))),
            numeric_cols[0],
        )
        temporal_col = temporal_cols[0] if temporal_cols else None
        series_col = None
        if series_cols:
            preferred = next(
                (col for col in series_cols if any(token in col.lower() for token in ("sku", "store", "product", "category", "region", "name", "customer"))),
                series_cols[0],
            )
            cardinality = len({str(row.get(preferred)) for row in rows[:200]})
            if 1 < cardinality <= 25:
                series_col = preferred

        mark_type = self._requested_chart_mark(question, answer, temporal_col)

        if mark_type == "arc" and len(rows) < 2:
            return None

        encoding = {}
        if mark_type == "arc":
            category_col = series_col or next(
                (col for col in category_cols if col != value_col),
                category_cols[0] if category_cols else columns[0],
            )
            encoding = {
                "theta": {"field": value_col, "type": "quantitative", "aggregate": "sum", "stack": True},
                "color": {"field": category_col, "type": "nominal", "title": self._humanize_field_name(category_col)},
                "tooltip": [
                    {"field": category_col, "type": "nominal", "title": "Store"},
                    {"field": value_col, "type": "quantitative", "aggregate": "sum", "title": "Sales Qty", "format": ",.0f"},
                ],
            }
        else:
            x_field = temporal_col or series_col or (category_cols[0] if category_cols else columns[0])
            if temporal_col:
                period_values = [str(row.get(temporal_col, "")) for row in rows[:20]]
                if period_values and all(
                    re.match(r"^[A-Za-z]{3}-\d{4}$", value) for value in period_values if value
                ):
                    x_type = "ordinal"
                else:
                    x_type = "temporal"
            elif all(self._is_month_label(str(row.get(x_field, ""))) for row in rows[:20]):
                x_type = "ordinal"
            else:
                x_type = "nominal"
            encoding = {
                "x": {"field": x_field, "type": x_type, "title": self._humanize_field_name(x_field)},
                "y": {"field": value_col, "type": "quantitative", "title": self._humanize_field_name(value_col), "aggregate": "sum"},
            }
            tooltip_fields = [
                {"field": x_field, "type": x_type, "title": self._humanize_field_name(x_field)},
                {"field": value_col, "type": "quantitative", "title": self._humanize_field_name(value_col)},
            ]
            for extra_col in numeric_cols:
                if extra_col != value_col:
                    tooltip_fields.append(
                        {"field": extra_col, "type": "quantitative", "title": self._humanize_field_name(extra_col)}
                    )
            encoding["tooltip"] = tooltip_fields
            if series_col and temporal_col:
                encoding["color"] = {"field": series_col, "type": "nominal", "title": series_col}

        title = None

        return {
            "title": title,
            "kind": "vega-lite",
            "spec": self._sanitize_vega_spec({
                "$schema": VEGA_LITE_SCHEMA,
                "width": 400,
                "height": 320,
                "data": {"values": rows[:200]},
                "mark": (
                    {"type": "arc", "innerRadius": 48, "outerRadius": 120, "stroke": "#fff", "strokeWidth": 1}
                    if mark_type == "arc"
                    else {"type": mark_type, "point": mark_type == "line"}
                ),
                "encoding": encoding,
            }),
        }

    def _merge_spec_with_data(self, spec: dict, rows: Optional[list[dict]]) -> dict:
        merged = json.loads(json.dumps(spec, default=str))
        if rows:
            sanitized_rows = self._normalize_row_values(rows)
            data_section = merged.get("data")
            if isinstance(data_section, dict):
                if "values" not in data_section and "url" not in data_section:
                    merged["data"] = {**data_section, "values": sanitized_rows}
                elif "values" in data_section:
                    merged["data"]["values"] = sanitized_rows
            else:
                merged["data"] = {"values": sanitized_rows}
        return self._sanitize_vega_spec(merged)

    def _extract_charts(
        self,
        steps,
        messages,
        run_id: Optional[str],
        question: str,
        answer: str,
        sql_previews=None,
    ) -> list[dict]:
        """
        Charts are shown when the user asks for one, or affirms a chart offer (e.g. "yes")
        and the agent reply describes a chart.
        """
        if not self._should_show_charts(question, answer):
            return []

        charts: list[dict] = []
        tables = self._extract_all_row_tables(steps, sql_previews, messages, answer, question)
        specs = self._extract_vega_specs_from_steps(steps)
        pbir_specs = [spec for spec in specs if self._is_pbir_visual_spec(spec)]
        vega_specs = [spec for spec in specs if self._is_vega_lite_spec(spec)]
        largest_table = max(tables, key=len) if tables else None

        for index, spec in enumerate(vega_specs, start=1):
            table = largest_table
            merged_spec = self._merge_spec_with_data(spec, table)
            title = merged_spec.get("title")
            if isinstance(title, dict):
                title = title.get("text")
            charts.append(
                {
                    "id": f"chart-{index}",
                    "title": title or f"Chart {index}",
                    "kind": "vega-lite",
                    "spec": merged_spec,
                }
            )

        for index, pbir_spec in enumerate(pbir_specs, start=1):
            table = largest_table
            if not table:
                continue
            converted = self._sanitize_vega_spec(self._pbir_to_vega_spec(pbir_spec, table) or {})
            if not converted.get("encoding"):
                continue
            charts.append(
                {
                    "id": f"pbir-chart-{index}",
                    "title": converted.get("title") or f"Chart {index}",
                    "kind": "vega-lite",
                    "spec": converted,
                }
            )

        for index, image in enumerate(self._extract_chart_images_from_messages(messages, run_id), start=1):
            charts.append(
                {
                    "id": f"image-{index}",
                    "title": "Chart",
                    "kind": "image",
                    "image_url": image["image_url"],
                }
            )

        if not charts and self._should_show_charts(question, answer):
            prepared_rows = self._prepare_chart_rows(tables, question, answer)
            if not prepared_rows:
                for table in sorted(tables, key=len, reverse=True):
                    prepared_rows = self._prepare_chart_rows([table], question, answer)
                    if prepared_rows:
                        break
            if prepared_rows:
                inferred = self._infer_chart_spec(question, answer, prepared_rows)
                if inferred:
                    charts.append({"id": "chart-inferred", **inferred})

        print(
            f"📊 Charts extracted: {len(charts)} "
            f"(tables={len(tables)}, vega_specs={len(vega_specs)}, pbir_specs={len(pbir_specs)})"
        )
        return charts

    def _run_question(
        self,
        question: str,
        timeout: int = DEFAULT_TIMEOUT,
        thread_name=None,
        preserve_thread: bool = True,
        include_steps: bool = False,
    ) -> dict:
        if not question.strip():
            raise ValueError("Question cannot be empty")

        client = self._get_openai_client(request_timeout=timeout)
        assistant = client.beta.assistants.create(model="not used", timeout=HTTP_REQUEST_TIMEOUT)
        thread = self._get_existing_or_create_new_thread(
            data_agent_url=self.data_agent_url,
            thread_name=thread_name,
        )

        client.beta.threads.messages.create(
            thread_id=thread['id'],
            role="user",
            content=question,
            timeout=HTTP_REQUEST_TIMEOUT,
        )

        run = client.beta.threads.runs.create(
            thread_id=thread['id'],
            assistant_id=assistant.id,
            timeout=HTTP_REQUEST_TIMEOUT,
        )

        run = self._monitor_run(client, thread['id'], run, timeout)
        print(f"Final status: {run.status}")

        steps = None
        if include_steps or run.status == "completed":
            steps = client.beta.threads.runs.steps.list(
                thread_id=thread['id'],
                run_id=run.id,
                timeout=HTTP_REQUEST_TIMEOUT,
            )

        messages = client.beta.threads.messages.list(
            thread_id=thread['id'],
            order="desc",
            limit=20,
            timeout=HTTP_REQUEST_TIMEOUT,
        )

        responses = self._extract_assistant_responses(messages, run_id=run.id)
        reframed_query = self._extract_reframed_query(steps, question) if steps else None

        sql_analysis = {"queries": [], "data_previews": [], "data_retrieval_query": None, "data_retrieval_query_index": None}
        if steps:
            sql_analysis = self._extract_sql_queries_with_data(steps)
            if not sql_analysis["queries"]:
                regex_queries = self._extract_sql_queries(steps)
                if regex_queries:
                    sql_analysis["queries"] = regex_queries
                    sql_analysis["data_retrieval_query"] = regex_queries[0]

        charts = []
        answer_text = "\n".join(responses) if responses else "No response received from the data agent."
        print("\n" + "=" * 80, flush=True)
        print(f"AGENT ANSWER for: {question}", flush=True)
        print("-" * 80, flush=True)
        print(answer_text, flush=True)
        print("=" * 80 + "\n", flush=True)
        if steps:
            charts = self._extract_charts(
                steps,
                messages,
                run.id,
                question,
                answer_text,
                sql_analysis.get("data_previews"),
            )

        self._maybe_cleanup_thread(client, thread, preserve_thread=preserve_thread)

        return {
            "question": question,
            "answer": answer_text,
            "charts": charts,
            "run_status": run.status,
            "reframed_query": reframed_query,
            "sql_queries": sql_analysis["queries"],
            "sql_data_previews": sql_analysis["data_previews"],
            "data_retrieval_query": sql_analysis["data_retrieval_query"],
            "thread": thread,
            "run": run,
            "steps": steps,
            "messages": messages,
            "timestamp": time.time(),
            "timeout": timeout,
            "success": run.status == "completed",
        }

    def ask_with_details(
        self,
        question: str,
        timeout: int = DEFAULT_TIMEOUT,
        thread_name=None,
        preserve_thread: bool = True,
    ) -> dict:
        """Ask a question and return answer plus run metadata (SQL, reframed query, status)."""
        print(f"\n🔍 Asking with details: {question}")
        try:
            return self._run_question(
                question=question,
                timeout=timeout,
                thread_name=thread_name,
                preserve_thread=preserve_thread,
                include_steps=True,
            )
        except Exception as e:
            logger.error("Error calling data agent: %s", e)
            return {
                "question": question,
                "answer": self._format_fabric_error(e),
                "run_status": "failed",
                "reframed_query": None,
                "sql_queries": [],
                "sql_data_previews": [],
                "data_retrieval_query": None,
                "charts": [],
                "success": False,
                "error": str(e),
                "timestamp": time.time(),
                "timeout": timeout,
            }

    def ask(self, question: str, timeout: int = DEFAULT_TIMEOUT, thread_name = None, preserve_thread: bool = False) -> str:
        """
        Ask a question to the Fabric Data Agent.
        
        Args:
            question (str): The question to ask
            timeout (int): Maximum time to wait for response in seconds
            thread_name (str, optional): The name of the thread to use

        Returns:
            str: The response from the data agent
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")
        
        print(f"\n Asking: {question}")
        
        try:
            result = self._run_question(
                question=question,
                timeout=timeout,
                thread_name=thread_name,
                preserve_thread=preserve_thread or bool(thread_name),
                include_steps=False,
            )
            return result["answer"] if not self.is_fabric_access_error(result["answer"]) else self._format_fabric_error(result["answer"])
        except Exception as e:
            logger.error("Error calling data agent: %s", e)
            return self._format_fabric_error(e)
    
    def get_run_details(self, question: str, thread_name=None, timeout: int = DEFAULT_TIMEOUT) -> dict:
        """
        Ask a question and return detailed run information including steps.
        
        Args:
            question (str): The question to ask
            
        Returns:
            dict: Detailed response including run steps, metadata, and SQL queries if lakehouse data source
        """
        print(f"\n🔍 Getting detailed run info for: {question}")
        
        try:
            result = self.ask_with_details(
                question=question,
                timeout=timeout,
                thread_name=thread_name,
                preserve_thread=bool(thread_name),
            )
            if result.get("error"):
                return {"error": result["error"]}

            messages = result.get("messages")
            sql_previews = list(result.get("sql_data_previews") or [])

            if messages:
                messages_data = messages.model_dump()
                assistant_messages = [msg for msg in messages_data.get('data', []) if msg.get('role') == 'assistant']
                if assistant_messages:
                    latest_message = assistant_messages[-1]
                    content = latest_message.get('content', [])
                    if content:
                        text_content = ""
                        if isinstance(content[0], dict) and 'text' in content[0]:
                            text_value = content[0]['text']
                            text_content = text_value.get('value', str(text_value)) if isinstance(text_value, dict) else str(text_value)
                        else:
                            text_content = str(content[0])

                        text_data_preview = self._extract_data_from_text_response(text_content)
                        if text_data_preview and (not sql_previews or not any(sql_previews)):
                            sql_previews = [text_data_preview]

            response = {
                "question": result["question"],
                "run_status": result["run_status"],
                "reframed_query": result.get("reframed_query"),
                "run_steps": result["steps"].model_dump() if result.get("steps") else {},
                "messages": messages.model_dump() if messages else {},
                "timestamp": result["timestamp"],
            }

            if result.get("sql_queries"):
                response["sql_queries"] = result["sql_queries"]
                response["sql_data_previews"] = sql_previews
                response["data_retrieval_query"] = result.get("data_retrieval_query")

            return response
            
        except Exception as e:
            print(f"❌ Error getting run details: {e}")
            return {"error": str(e)}

    def get_raw_run_response(self, question: str, timeout: int = DEFAULT_TIMEOUT, thread_name = None) -> dict:
        """
        Ask a question and return the complete raw response including all run details.
        This is useful when you need to parse or analyze the full response structure.
        
        Args:
            question (str): The question to ask
            timeout (int): Maximum time to wait for response in seconds
            
        Returns:
            dict: Complete raw response with run steps, messages, and metadata
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")
        
        print(f"\n🔍 Getting raw response for: {question}")
        
        try:
            result = self._run_question(
                question=question,
                timeout=timeout,
                thread_name=thread_name,
                preserve_thread=bool(thread_name),
                include_steps=True,
            )

            messages = result.get("messages")
            return {
                "question": question,
                "run": result["run"].model_dump() if result.get("run") else {},
                "steps": result["steps"].model_dump() if result.get("steps") else {},
                "messages": messages.model_dump() if messages else {},
                "timestamp": result["timestamp"],
                "timeout": timeout,
                "success": result["success"],
                "thread": result.get("thread"),
                "reframed_query": result.get("reframed_query"),
            }
            
        except Exception as e:
            print(f"❌ Error getting raw response: {e}")
            return {
                "question": question,
                "error": str(e),
                "timestamp": time.time(),
                "success": False
            }

    def _extract_sql_queries_with_data(self, steps) -> dict:
        """
        Extract SQL queries from run steps using direct JSON parsing and output analysis.
        
        Args:
            steps: The run steps from the OpenAI API
            
        Returns:
            dict: Contains queries, data previews, and which query retrieved data
        """
        sql_queries = []
        data_previews = []
        data_retrieval_query = None
        data_retrieval_query_index = None
        
        try:
            for step_idx, step in enumerate(steps.data):
                if hasattr(step, 'step_details') and step.step_details:
                    step_details = step.step_details
                    
                    # Check for tool calls which typically contain the SQL queries
                    if hasattr(step_details, 'tool_calls') and step_details.tool_calls:
                        for tool_idx, tool_call in enumerate(step_details.tool_calls):
                            # Extract SQL from function arguments
                            sql_from_args = self._extract_sql_from_function_args(tool_call)
                            if sql_from_args:
                                sql_queries.extend(sql_from_args)
                            
                            # Extract SQL from tool call output (where it's actually located in Fabric)
                            sql_from_output = self._extract_sql_from_output(tool_call)
                            if sql_from_output:
                                sql_queries.extend(sql_from_output)
                            
                            # Extract data from tool call output
                            data_preview = self._extract_structured_data_from_output(tool_call)
                            if data_preview:
                                # If we found data and SQL in this step, it's likely the retrieval query
                                if sql_from_args or sql_from_output:
                                    all_sql_this_call = sql_from_args + sql_from_output
                                    data_retrieval_query = all_sql_this_call[-1] if all_sql_this_call else None
                                    data_retrieval_query_index = len(sql_queries)
                            
                            data_previews.append(data_preview)
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract SQL queries: {e}")
        
        # Remove duplicates while preserving order
        unique_queries = list(dict.fromkeys(sql_queries))
        
        return {
            "queries": unique_queries,
            "data_previews": data_previews,
            "data_retrieval_query": data_retrieval_query,
            "data_retrieval_query_index": data_retrieval_query_index
        }

    def _extract_sql_from_function_args(self, tool_call) -> list:
        """
        Extract SQL queries from tool call function arguments.
        
        Args:
            tool_call: OpenAI tool call object
            
        Returns:
            list: SQL queries found
        """
        import json
        sql_queries = []
        
        try:
            if hasattr(tool_call, 'function') and tool_call.function:
                if hasattr(tool_call.function, 'arguments'):
                    args_str = tool_call.function.arguments
                    
                    # Parse the arguments JSON
                    args = json.loads(args_str)
                    
                    if isinstance(args, dict):
                        # Common keys where SQL queries are stored in Fabric Data Agents
                        sql_keys = ['sql', 'query', 'sql_query', 'statement', 'command', 'code']
                        
                        for key in sql_keys:
                            if key in args and args[key]:
                                sql_query = str(args[key]).strip()
                                if sql_query and len(sql_query) > 10:  # Basic validation
                                    sql_queries.append(sql_query)
                        
                        # Also check for nested structures
                        for key, value in args.items():
                            if isinstance(value, dict):
                                for nested_key in sql_keys:
                                    if nested_key in value and value[nested_key]:
                                        sql_query = str(value[nested_key]).strip()
                                        if sql_query and len(sql_query) > 10:
                                            sql_queries.append(sql_query)
        
        except (json.JSONDecodeError, AttributeError) as e:
            # If JSON parsing fails, fall back to basic string search
            try:
                args_str = str(tool_call.function.arguments)
                # Look for common SQL patterns in the string
                if any(keyword in args_str.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                    # Use minimal regex as fallback
                    import re
                    sql_pattern = r'"(?:sql|query|statement|code)"\s*:\s*"([^"]+)"'
                    matches = re.findall(sql_pattern, args_str, re.IGNORECASE)
                    sql_queries.extend([match.strip() for match in matches if len(match.strip()) > 10])
            except Exception as parse_error:
                print(f"⚠️ Warning: Could not parse tool call arguments: {parse_error}")
        
        return sql_queries

    def _extract_sql_from_output(self, tool_call) -> list:
        """
        Extract SQL queries from tool call output.
        
        Args:
            tool_call: OpenAI tool call object
            
        Returns:
            list: SQL queries found in output
        """
        import json
        import re
        sql_queries = []
        
        try:
            if hasattr(tool_call, 'output') and tool_call.output:
                output_str = str(tool_call.output)
                
                # First try to parse as JSON
                try:
                    output_json = json.loads(output_str)
                    
                    if isinstance(output_json, dict):
                        # Look for SQL in common keys
                        sql_keys = ['sql', 'query', 'sql_query', 'statement', 'command', 'code', 'generated_code']
                        for key in sql_keys:
                            if key in output_json and output_json[key]:
                                sql_query = str(output_json[key]).strip()
                                if sql_query and len(sql_query) > 10:
                                    sql_queries.append(sql_query)
                        
                        # Check nested structures
                        for key, value in output_json.items():
                            if isinstance(value, dict):
                                for nested_key in sql_keys:
                                    if nested_key in value and value[nested_key]:
                                        sql_query = str(value[nested_key]).strip()
                                        if sql_query and len(sql_query) > 10:
                                            sql_queries.append(sql_query)
                
                except json.JSONDecodeError:
                    # If not JSON, use regex to find SQL patterns
                    pass
                
                # Always also try regex as backup/additional method
                if any(keyword in output_str.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM']):
                    # Enhanced regex patterns for SQL extraction
                    sql_patterns = [
                        r'"(?:sql|query|statement|code|generated_code)"\s*:\s*"([^"]+)"',
                        r"'(?:sql|query|statement|code|generated_code)'\s*:\s*'([^']+)'",
                        r'(SELECT\s+.*?FROM\s+.*?)(?=\s*[;}"\'\n]|\s*$)',
                        r'(INSERT\s+INTO\s+.*?)(?=\s*[;}"\'\n]|\s*$)',
                        r'(UPDATE\s+.*?SET\s+.*?)(?=\s*[;}"\'\n]|\s*$)',
                        r'(DELETE\s+FROM\s+.*?)(?=\s*[;}"\'\n]|\s*$)'
                    ]
                    
                    for pattern in sql_patterns:
                        matches = re.findall(pattern, output_str, re.IGNORECASE | re.DOTALL)
                        for match in matches:
                            clean_query = match.strip().replace('\\n', '\n').replace('\\t', '\t')
                            clean_query = re.sub(r'\s+', ' ', clean_query)
                            if len(clean_query) > 10:
                                sql_queries.append(clean_query)
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract SQL from output: {e}")
        
        return sql_queries

    def _extract_structured_data_from_output(self, tool_call) -> list:
        """
        Extract structured data from tool call output using JSON parsing.
        
        Args:
            tool_call: OpenAI tool call object
            
        Returns:
            list: Formatted data lines
        """
        import json
        data_lines = []
        
        try:
            if hasattr(tool_call, 'output') and tool_call.output:
                output_str = str(tool_call.output)
                
                # Try to parse as JSON first
                try:
                    data = json.loads(output_str)
                    
                    if isinstance(data, list) and len(data) > 0:
                        # Handle list of records (typical query result)
                        if isinstance(data[0], dict):
                            headers = list(data[0].keys())
                            data_lines.append("| " + " | ".join(headers) + " |")
                            data_lines.append("|" + "---|" * len(headers))
                            
                            for row in data[:10]:  # Limit to first 10 rows
                                values = [str(row.get(h, "")) for h in headers]
                                data_lines.append("| " + " | ".join(values) + " |")
                    
                    elif isinstance(data, dict):
                        # Handle single record or structured response
                        if 'data' in data and isinstance(data['data'], list):
                            # Nested data structure
                            return self._format_list_data(data['data'])
                        elif 'results' in data and isinstance(data['results'], list):
                            # Results structure
                            return self._format_list_data(data['results'])
                        else:
                            # Single record
                            data_lines.append("| Key | Value |")
                            data_lines.append("|---|---|")
                            for key, value in data.items():
                                data_lines.append(f"| {key} | {str(value)} |")
                
                except json.JSONDecodeError:
                    # If not JSON, look for other structured formats
                    data_lines = self._extract_data_preview(output_str)
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract structured data: {e}")
        
        return data_lines

    def _extract_markdown_table(self, text: str) -> str:
        """
        Extract raw markdown table from the assistant's text response.
        
        Args:
            text (str): The assistant's text response
            
        Returns:
            str: Raw markdown table if found, or empty string if no table found
        """
        lines = text.split('\n')
        table_lines = []
        in_table = False
        header_found = False
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check if this line contains markdown table separators
            if '|' in line_stripped and ('---' in line_stripped or '-' in line_stripped and line_stripped.count('-') > 3):
                table_lines.append(line)
                in_table = True
                header_found = True
            elif '|' in line_stripped and (in_table or not header_found):
                # This is a table row (header or data row)
                table_lines.append(line)
                in_table = True
            elif in_table and line_stripped == '':
                # Empty line - might continue table, add it but don't break yet
                table_lines.append(line)
            elif in_table and '|' not in line_stripped and line_stripped != '':
                # Non-table line after we were in a table - end of table
                break
        
        # Clean up trailing empty lines
        while table_lines and table_lines[-1].strip() == '':
            table_lines.pop()
        
        # Return the raw markdown table if we found at least a header and separator
        if len(table_lines) >= 2:
            return '\n'.join(table_lines)
        else:
            return ""

    def _extract_data_from_text_response(self, text_content: str) -> list:
        """
        Extract structured data from the assistant's text response.
        First tries to find raw markdown tables, then falls back to numbered list parsing.
        
        Args:
            text_content (str): The text content from the assistant
            
        Returns:
            list: Formatted data lines (raw markdown table as single item, or parsed rows)
        """
        import re
        
        # First, try to extract a raw markdown table
        markdown_table = self._extract_markdown_table(text_content)
        if markdown_table:
            # Return the raw markdown table as a single formatted block
            return [markdown_table]
        
        # Fallback to numbered list parsing (existing logic)
        data_lines = []
        
        try:
            lines = text_content.split('\n')
            
            # Look for numbered lists with data (like the example output)
            numbered_pattern = r'^\d+\.\s+'
            data_rows = []
            
            for line in lines:
                line = line.strip()
                if re.match(numbered_pattern, line):
                    # Remove the number prefix
                    clean_line = re.sub(numbered_pattern, '', line)
                    data_rows.append(clean_line)
            
            if data_rows and len(data_rows) > 0:
                # Try to parse the structured data from the text
                first_row = data_rows[0]
                if ':' in first_row:
                    # Parse key-value format
                    # Example: "Date: 4/29/2020, State: WI, Positive: 7,660, ..."
                    
                    # Extract headers from first row
                    headers = []
                    values_first_row = []
                    
                    pairs = first_row.split(', ')
                    for pair in pairs:
                        if ':' in pair:
                            key, value = pair.split(':', 1)
                            headers.append(key.strip())
                            values_first_row.append(value.strip())
                    
                    if headers:
                        # Create table format
                        data_lines.append("| " + " | ".join(headers) + " |")
                        data_lines.append("|" + "---|" * len(headers))
                        
                        # Add first row
                        data_lines.append("| " + " | ".join(values_first_row) + " |")
                        
                        # Parse remaining rows
                        for row in data_rows[1:]:
                            values = []
                            pairs = row.split(', ')
                            for pair in pairs:
                                if ':' in pair:
                                    _, value = pair.split(':', 1)
                                    values.append(value.strip())
                            
                            if len(values) == len(headers):
                                data_lines.append("| " + " | ".join(values) + " |")
                            
                        return data_lines
                
                # If we couldn't parse structured format, return the raw rows as-is
                if not data_lines and data_rows:
                    # Just show the numbered list data
                    return [f"Row {i+1}: {row}" for i, row in enumerate(data_rows)]
            
            # Alternative: Look for table-like structures in the text
            # Check if there are lines that look like table rows
            potential_table_lines = []
            for line in lines:
                line = line.strip()
                # Look for lines with multiple separators that could be table data
                if line and ('|' in line or line.count(',') >= 2 or line.count(':') >= 2):
                    potential_table_lines.append(line)
            
            if potential_table_lines and not data_lines:
                return potential_table_lines[:10]  # Return first 10 lines
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract data from text response: {e}")
        
        return data_lines

    def _format_list_data(self, data_list) -> list:
        """
        Format a list of data records into table format.
        """
        data_lines = []
        
        if len(data_list) > 0 and isinstance(data_list[0], dict):
            headers = list(data_list[0].keys())
            data_lines.append("| " + " | ".join(headers) + " |")
            data_lines.append("|" + "---|" * len(headers))
            
            for row in data_list[:10]:  # Limit to first 10 rows
                values = [str(row.get(h, "")) for h in headers]
                data_lines.append("| " + " | ".join(values) + " |")
        
        return data_lines

    def _extract_data_preview(self, text: str) -> list:
        """
        Extract data preview from text output.
        
        Args:
            text (str): Text to search for tabular data
            
        Returns:
            list: List of data rows found
        """
        import re
        import json
        
        data_lines = []
        
        try:
            # Look for JSON-like data structures
            json_pattern = r'\[[\s\S]*?\]'
            json_matches = re.findall(json_pattern, text)
            
            for match in json_matches:
                try:
                    # Try to parse as JSON
                    data = json.loads(match)
                    if isinstance(data, list) and len(data) > 0:
                        # Convert to readable format
                        if isinstance(data[0], dict):
                            # List of dictionaries (typical query result)
                            headers = list(data[0].keys())
                            data_lines.append("| " + " | ".join(headers) + " |")
                            data_lines.append("|" + "---|" * len(headers))
                            
                            for row in data[:10]:  # Limit to first 10 rows
                                values = [str(row.get(h, "")) for h in headers]
                                data_lines.append("| " + " | ".join(values) + " |")
                        break  # Found valid JSON data
                except json.JSONDecodeError:
                    continue
            
            # If no JSON found, look for pipe-separated tables
            if not data_lines:
                lines = text.split('\n')
                table_lines = []
                
                for line in lines:
                    # Look for lines that contain multiple pipe characters (table format)
                    if line.count('|') >= 2:
                        table_lines.append(line.strip())
                    elif table_lines and line.strip() == "":
                        # End of table
                        break
                    elif table_lines and not line.strip().startswith('|'):
                        # Non-table line after table started
                        break
                
                if table_lines:
                    data_lines = table_lines[:15]  # Limit to first 15 lines
            
            # Look for CSV-like data
            if not data_lines:
                lines = text.split('\n')
                csv_lines = []
                
                for line in lines:
                    # Look for comma-separated values with consistent column count
                    if ',' in line and len(line.split(',')) >= 2:
                        csv_lines.append(line.strip())
                        if len(csv_lines) >= 10:  # Limit preview
                            break
                    elif csv_lines:
                        break
                
                if len(csv_lines) > 1:  # At least header + one data row
                    data_lines = csv_lines
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract data preview: {e}")
        
        return data_lines

    def _extract_sql_queries(self, steps) -> list:
        """
        Extract SQL queries from run steps when lakehouse data source is used.
        
        Args:
            steps: The run steps from the OpenAI API
            
        Returns:
            list: List of SQL queries found in the steps
        """
        sql_queries = []
        
        try:
            for step in steps.data:
                if hasattr(step, 'step_details') and step.step_details:
                    step_details = step.step_details
                    
                    # Check for tool calls that might contain SQL
                    if hasattr(step_details, 'tool_calls') and step_details.tool_calls:
                        for tool_call in step_details.tool_calls:
                            # Look for SQL queries in tool call details
                            if hasattr(tool_call, 'function') and tool_call.function:
                                if hasattr(tool_call.function, 'arguments'):
                                    args_str = str(tool_call.function.arguments)
                                    # Look for SQL patterns in arguments
                                    sql_queries.extend(self._find_sql_in_text(args_str))
                            
                            # Check tool call outputs for SQL
                            if hasattr(tool_call, 'output') and tool_call.output:
                                output_str = str(tool_call.output)
                                sql_queries.extend(self._find_sql_in_text(output_str))
                    
                    # Check step details for any SQL content
                    step_str = str(step_details)
                    sql_queries.extend(self._find_sql_in_text(step_str))
        
        except Exception as e:
            print(f"⚠️ Warning: Could not extract SQL queries: {e}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_queries = []
        for query in sql_queries:
            if query not in seen:
                seen.add(query)
                unique_queries.append(query)
        
        return unique_queries

    def _find_sql_in_text(self, text: str) -> list:
        """
        Find SQL queries in text using pattern matching.
        
        Args:
            text (str): Text to search for SQL queries
            
        Returns:
            list: List of SQL queries found
        """
        import re
        
        sql_queries = []
        
        # Common SQL keywords that indicate a query
        sql_patterns = [
            r'(SELECT\s+.*?FROM\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\)|\s*,)',
            r'(INSERT\s+INTO\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(UPDATE\s+.*?SET\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(DELETE\s+FROM\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(CREATE\s+TABLE\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(ALTER\s+TABLE\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))',
            r'(DROP\s+TABLE\s+.*?)(?=\s*;|\s*$|\s*\}|\s*\))'
        ]
        
        for pattern in sql_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                # Clean up the SQL query
                clean_query = match.strip().replace('\n', ' ').replace('\t', ' ')
                clean_query = re.sub(r'\s+', ' ', clean_query)  # Normalize whitespace
                if len(clean_query) > 10:  # Filter out very short matches
                    sql_queries.append(clean_query)
        
        return sql_queries


def is_fabric_access_error(message: str) -> bool:
    return FabricDataAgentClient.is_fabric_access_error(message)


def is_retryable_fabric_error(message: str) -> bool:
    lowered = str(message or "").lower()
    return (
        "itemnotfound" in lowered
        or "error code: 404" in lowered
        or "error code: 403" in lowered
        or "insufficientprivileges" in lowered
        or ("user id" in lowered and "don't match" in lowered)
        or "could not found the requested item" in lowered
    )


def format_fabric_error(error: Exception | str, user_email: Optional[str] = None) -> str:
    return FabricDataAgentClient.format_fabric_error(error, user_email)


def main(questions: list, raw_response: bool = False, thread_name = None):
    """
    Example usage of the Fabric Data Agent Client.
    """
    # Configuration - Update these with your actual values
    TENANT_ID = os.getenv("TENANT_ID", "your-tenant-id-here")
    DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "your-data-agent-url-here")
    
    # Validate configuration
    if TENANT_ID == "your-tenant-id-here" or DATA_AGENT_URL == "your-data-agent-url-here":
        print("❌ Please update TENANT_ID and DATA_AGENT_URL with your actual values")
        print("\nYou can either:")
        print("1. Edit this script and update the values directly")
        print("2. Set environment variables: TENANT_ID and DATA_AGENT_URL")
        print("3. Create a .env file with these variables")
        return
    
    try:
        # Initialize the client (this will trigger authentication)
        client = FabricDataAgentClient(
            tenant_id=TENANT_ID,
            data_agent_url=DATA_AGENT_URL
        )
        
        print("\n" + "="*60)
        print("🤖 Fabric Data Agent Client - Ready!")
        print("="*60)
        
        for i, question in enumerate(questions, 1):
            if raw_response == True: #printing (mostly) raw response
                response = client.get_raw_run_response(question, thread_name=thread_name)
                print(f"\nConversation in thread '{response['thread']['name']}, thread_id: {response['thread']['id']}':\n" + "-" * 50)
                for message in response['messages']['data']:
                    print(f"Role: {message['role']}, Content: \n{message['content'][0]['text']['value']}\n---")
                print(f"\n💬 json Response:")
                print("-" * 50)
                print(json.dumps(response, indent=2, default=str))
                print("-" * 50)
            else:
                response = client.ask(question, thread_name=thread_name)
                print(f"\n💬 Response:")
                print("-" * 50)
                print(response)
                print("-" * 50)
            
            # Wait between requests
            if i < len(questions):
                n = 1
                print(f"\nWaiting {n} seconds before next question...")
                time.sleep(n)
        
        print("\n✅ All examples completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    # Example questions
    
    thread_name = "example_threadname"
    questions = [
        "What data is available in the lakehouse?",
        "Show me the top 5 records from any available table",
        "What are the column names and types in the main tables?"
    ]
    main(questions, raw_response=True, thread_name=thread_name)
