# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import os
from typing import Optional, Tuple, List
import requests
import httpx

from llama_stack_client import LlamaStackClient
from openai import OpenAI

class LlamaStackApi:
    def __init__(self):
        self.client = LlamaStackClient(
            base_url=os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
        )

    def run_scoring(self, row, scoring_function_ids: list[str], scoring_params: Optional[dict]):
        """Run scoring on a single row"""
        if not scoring_params:
            scoring_params = {fn_id: None for fn_id in scoring_function_ids}
        return self.client.scoring.score(input_rows=[row], scoring_functions=scoring_params)

    def create_openai_client(self, base_url: str, api_token: str) -> OpenAI:
        """Create an OpenAI client for the F5 AI Guardrails endpoint"""
        return OpenAI(
            base_url=base_url,
            api_key=api_token,
            http_client=httpx.Client(verify=False),
        )

    def create_client_with_url(self, base_url: str, api_token: str = "") -> LlamaStackClient:
        """Create a LlamaStackClient with custom base URL and optional API token"""
        kwargs = {"base_url": base_url}
        if base_url.startswith("https://"):
            kwargs["http_client"] = httpx.Client(verify=False)
        if api_token:
            kwargs["api_key"] = api_token
        return LlamaStackClient(**kwargs)

    def validate_llamastack_endpoint(self, url: str, api_token: str = "") -> Tuple[bool, Optional[List], Optional[str]]:
        """
        Validate if the URL is a LlamaStack endpoint and fetch models.

        Returns:
            Tuple[bool, Optional[List], Optional[str]]:
            (is_valid, models_list, error_message)
        """
        try:
            url = url.rstrip('/')

            if not url.startswith(('http://', 'https://')):
                return False, None, "XC URL must start with http:// or https://"

            client = self.create_client_with_url(url, api_token)

            models = client.models.list()

            if not models:
                return False, None, "XC URL must be a LlamaStack endpoint"

            return True, models, None

        except requests.exceptions.ConnectionError:
            return False, None, "Cannot connect to XC URL. Please check the URL and network connectivity."
        except requests.exceptions.Timeout:
            return False, None, "Connection to XC URL timed out. Please try again."
        except Exception as e:
            return False, None, f"Connection failed: {type(e).__name__}: {e}"

    def fetch_models_from_url(self, url: str, api_token: str = "") -> Tuple[bool, Optional[List], Optional[str]]:
        """
        Fetch models from a custom LlamaStack URL.

        Returns:
            Tuple[bool, Optional[List], Optional[str]]:
            (success, models_list, error_message)
        """
        return self.validate_llamastack_endpoint(url, api_token)

llama_stack_api = LlamaStackApi()
